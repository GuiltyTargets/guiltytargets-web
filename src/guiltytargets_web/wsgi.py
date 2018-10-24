# -*- coding: utf-8 -*-

"""A WSGI application for GuiltyTargets.

Both the application and the celery worker have to be running at the same time.

1. Run rabbitmq in the background

2. Run application with:

.. code-block:: bash

    $ python -m guiltytargets_web.wsgi

3. Run celery worker with:

.. code-block:: bash

    $ celery worker -A guiltytargets_web.wsgi.celery -l INFO # TODO: not sure

"""
import logging
import os
import time
from typing import List, Tuple

import click
from celery import Celery
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from flask import Flask, Markup, flash, jsonify, redirect, render_template, url_for
from flask_bootstrap import Bootstrap

from guiltytargets.pipeline import rank_targets
from guiltytargets_web.forms import Form
from ppi_network_annotation.model.attribute_network import AttributeNetwork
from ppi_network_annotation.model.labeled_network import LabeledNetwork
from ppi_network_annotation.pipeline import generate_ppi_network

celery_logger = get_task_logger(__name__)
logger = logging.getLogger(__name__)

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

# -*- coding: utf-8 -*-

"""Forms for GuiltyTargets-Web."""


@celery.task(name=RUN_GUILTYTARGETS)
def run(targets: List[str],
        ppi_graph_path: str,
        dge_path: str,
        entrez_id_header: str,
        log2_fold_change_header: str,
        adj_p_header: str,
        base_mean_header: str,
        entrez_delimiter: str,
        output_directory: str):
    """Run the GuiltyTargets pipeline."""
    start_time = time.time()

    assert os.path.exists(ppi_graph_path), f'ppi graph file does not exist: {ppi_graph_path}'
    assert os.path.exists(dge_path), f'differential expression file does not exist: {dge_path}'


    click.secho('generating PPI network', color='cyan')
    network = generate_ppi_network(
        ppi_graph_path=ppi_graph_path,
        dge_path=dge_path,
        entrez_id_header=entrez_id_header,
        log2_fold_change_header=log2_fold_change_header,
        adj_p_header=adj_p_header,
        base_mean_header=base_mean_header,
        entrez_delimiter=entrez_delimiter,
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

    os.makedirs(output_directory, exist_ok=True)
    auc_df, probs_df = rank_targets(
        network=network,
        targets=targets,
        directory=output_directory,
    )

    rv['auc'] = auc_df.to_json()
    rv['probs'] = probs_df.to_json()
    rv['time'] = time.time() - start_time

    return rv


def process_form(form: Form) -> Tuple:  # TODO: implement
    targets = [
        line.strip()
        for line in form.entrez_gene_identifiers.data.splitlines()
    ]

    # send the task to the queue (will happen asynchronously)
    return (
        targets,
        form.ppi_graph.data
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

    args = process_form(form)
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
