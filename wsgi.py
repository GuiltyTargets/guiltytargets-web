# -*- coding: utf-8 -*-

"""A WSGI application for GuiltyTargets.

Both the application and the celery worker have to be running at the same time.

1. Run rabbitmq in the background

2. Run application with:

.. code-block:: bash

    $ pipenv run gunicorn -b 0.0.0.0:5000 wsgi:app

3. Run celery worker with:

.. code-block:: bash

    $ pipenv run celery worker -A wsgi.celery -l INFO

"""
import logging
import os
import tempfile
import time
from typing import Dict, List, Tuple

import pandas as pd
from celery import Celery
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from flask import Flask, Markup, flash, jsonify, redirect, render_template, url_for
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms.fields import RadioField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired

from guiltytargets.pipeline import rank_targets
from ppi_network_annotation.model import AttributeNetwork, Gene, LabeledNetwork
from ppi_network_annotation.parsers import handle_dataframe
from ppi_network_annotation.pipeline import generate_ppi_network

celery_logger = get_task_logger(__name__)
logger = logging.getLogger(__name__)

HERE = os.path.abspath(os.path.dirname(__file__))

STRING_PATH = os.path.abspath(os.path.join(HERE, 'data', 'string.edgelist'))
HIPPIE_PATH = os.path.abspath(os.path.join(HERE, 'data', 'hippie.edgelist'))

PPI_PATH_CHOICES = [
    (path, name)
    for path, name in [(STRING_PATH, 'STRING'), (HIPPIE_PATH, 'HIPPIE')]
    if os.path.exists(path)
]

assert PPI_PATH_CHOICES, 'no files available'

##############################
# Configuration option names #
##############################

#: The name of the configuration option for the Celery broker URL.
CELERY_BROKER_URL = 'CELERY_BROKER_URL'
CELERY_RESULT_BACKEND = 'CELERY_RESULT_BACKEND'

config = {

    # The broker is the address of the message queue that mediates communication between the Flask app and the worker
    # In this example, RabbitMQ is used over AMPQ protocol
    # See: http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html#choosing-a-broker
    CELERY_BROKER_URL: os.environ.get(CELERY_BROKER_URL, 'amqp://localhost'),

    # The result backend stores the results of tasks.
    # In this example, SQLAlchemy is used with SQLite.
    # See: http://celery.readthedocs.io/en/latest/userguide/configuration.html#task-result-backend-settings
    CELERY_RESULT_BACKEND: os.environ.get(CELERY_RESULT_BACKEND, 'db+sqlite:///results.sqlite'),

}

#####################
# Celery task names #
#####################
RUN_GUILTYTARGETS = 'run-guiltytargets'

# Create the Flask application
app = Flask(__name__)

# Update configuration. Might want to get from a config file or environment for different deployments
app.config.update(config)

# Set a random key for CSRF (for Flask-WTF)
app.secret_key = os.urandom(8)

# Add the Flask-Bootstrap extension
Bootstrap(app)

################
# Celery Stuff #
################

# Add Celery magic
celery = Celery(
    app.import_name,
    broker=app.config[CELERY_BROKER_URL],
    backend=app.config[CELERY_RESULT_BACKEND],
)


@celery.task(name=RUN_GUILTYTARGETS)
def run(targets: List[str], ppi_graph_path: str, dge_json: List[Dict]):
    """Run the GuiltyTargets pipeline."""
    start_time = time.time()

    assert os.path.exists(ppi_graph_path), f'ppi graph file does not exist: {ppi_graph_path}'

    dge_list = Gene.schema().load(dge_json, many=True)

    # stick the data in the temporary file
    # load the PPI network
    network = generate_ppi_network(
        ppi_graph_path=ppi_graph_path,
        dge_list=dge_list,
        max_adj_p=0.05,
        min_log2_fold_change=1.0,
        max_log2_fold_change=-1.0,
        ppi_edge_min_confidence=0.0,
    )
    labeled_network = LabeledNetwork(network)
    attribute_network = AttributeNetwork(network)

    rv = {
        'adjacency_list': network.get_adjlist(),
        'attribute_adjacency_list': attribute_network.get_attribute_mappings(),
        'label_mappings': labeled_network.get_index_labels(targets),
    }

    with tempfile.TemporaryDirectory() as output_directory:
        auc_df, probs_df = rank_targets(
            network=network,
            targets=targets,
            directory=output_directory,
        )

    rv['auc'] = auc_df.to_json()
    rv['probs'] = probs_df.to_json()
    rv['time'] = time.time() - start_time

    return rv


class Form(FlaskForm):
    """The form for using the GuiltyTargets pipeline."""

    entrez_gene_identifiers = TextAreaField(
        'Entrez Gene Identifiers',
        validators=[DataRequired()],
    )

    ppi_graph = RadioField(
        'PPI Graph',
        choices=PPI_PATH_CHOICES,
        default=HIPPIE_PATH,
    )

    file = FileField(
        'Differential Gene Expression File',
        validators=[DataRequired()],
    )

    entrez_id_column_name = StringField(
        'Entrez Gene Identifier Column Name',
        default='Gene.ID',
        validators=[DataRequired()],
    )

    log2_fold_change_column_name = StringField(
        'Log Fold Change Column Name',
        default='logFC',
        validators=[DataRequired()],
    )

    adj_p_column_name = StringField(
        'Adjusted P-value Column Name',
        default='adj.P.Val',
        validators=[DataRequired()],
    )

    entrez_delimiter = StringField(
        'Entrez delimiter',
        default='///',
        validators=[DataRequired()],
    )

    base_mean_column_name = StringField(
        'Base Mean Column Name',
    )

    separator = RadioField(
        'Separator',
        choices=[
            ('\t', 'My document is a TSV file'),
            (',', 'My document is a CSV file'),
        ],
        default='\t')

    #: The submit field
    submit = SubmitField('Upload')

    def get_target_list(self) -> List[str]:
        return [line.strip() for line in self.entrez_gene_identifiers.data.splitlines()]

    def get_dge_list(self) -> List[Gene]:
        df = pd.read_csv(self.file.data, sep=self.separator.data)
        return handle_dataframe(
            df,
            entrez_id_name=self.entrez_id_column_name.data,
            log2_fold_change_name=self.log2_fold_change_column_name.data,
            adjusted_p_value_name=self.adj_p_column_name.data,
            entrez_delimiter=self.entrez_delimiter.data,
            base_mean=(self.base_mean_column_name.data or None)
        )

    def prepare(self) -> Tuple[List[str], str, List[Dict]]:
        """"""
        targets = self.get_target_list()
        genes = self.get_dge_list()
        gene_json = Gene.schema().dump(genes, many=True)

        return (
            targets,
            self.ppi_graph.data,
            gene_json
        )


################
# Flask routes #
################

@app.route('/', methods=['GET', 'POST'])
def home():
    """Serve the home page."""
    form = Form()

    if not form.validate_on_submit():
        return render_template('index.html', form=form)

    args = form.prepare()
    task = celery.send_task(RUN_GUILTYTARGETS, args=args)

    # Send a message to the user so they can find their task
    flash(Markup(f'''Queued task <code><a href="{url_for('results', task=task.task_id)}">{task}</a></code>.'''))

    return render_template('index.html', form=form)


@app.route('/check/<task>', methods=['GET'])
def check(task: str):
    """Check the given task.

    :param task: The UUID of a task.
    """
    task = AsyncResult(task, app=celery)

    if not task.successful():
        return jsonify(
            task_id=task.task_id,
            status=task.status,
            result=task.result,
        )

    return jsonify(
        task_id=task.task_id,
        status=task.status
    )


@app.route('/results/<task>', methods=['GET'])
def results(task: str):
    """Check the given task.

    :param task: The UUID of a task.
    """
    task = AsyncResult(task, app=celery)

    if task.successful():
        return render_template('results.html', task=task)

    url = url_for('results', task=task.task_id)
    flash(Markup(f'Task <code><a href="{url}">{task}</a></code> is not yet complete.'), category='warning')
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)
