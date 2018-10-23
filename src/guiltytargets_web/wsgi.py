# -*- coding: utf-8 -*-

"""WSGI application for GuiltyTargets.

Both the application and the celery worker have to be running at the same time.

Run rabbitmq in the background

Run application with:

.. code-block:: bash

    $ python -m guiltytargets_web.wsgi

Run celery worker with:

.. code-block:: bash

    $ celery worker -A guiltytargets_web.wsgi.celery -l INFO # TODO: not sure

"""
import logging
import os
from typing import Tuple

from celery import Celery
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from flask import Flask, Markup, flash, jsonify, redirect, render_template, url_for
from flask_bootstrap import Bootstrap

from guiltytargets_web.forms import GuiltyTargetsForm
from guiltytargets_web.tasks import guiltytargets_pipeline

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


@celery.task(name=RUN_GUILTYTARGETS)
def run_guiltytargets(
        targets: list,
        ppi_graph_path: str,
        dge_path: str,
        entrez_id_header: str,
        l2fc_header: str,
        adjp_header: str,
        base_mean_header: str,
        split_char: str,
        output_dir: str
):
    return guiltytargets_pipeline(
        targets,
        ppi_graph_path,
        dge_path,
        entrez_id_header,
        l2fc_header,
        adjp_header,
        base_mean_header,
        split_char,
        output_dir
    )


def process_form(form: GuiltyTargetsForm) -> Tuple:  # TODO: implement
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
    guiltytargets_form = GuiltyTargetsForm()

    if guiltytargets_form.validate_on_submit():
        args = process_form(guiltytargets_form)
        task = celery.send_task(RUN_GUILTYTARGETS, args=args)
        url = url_for('results', task=task.task_id)
        flash(Markup(f'Queued task <code><a href="{url}">{task}</a></code>.'))
        return render_template('index.html', form=guiltytargets_form)

    return render_template('index.html', form=guiltytargets_form)


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

    if not task.successful():
        url = url_for('results', task=task.task_id)
        flash(Markup(f'Task <code><a href="{url}">{task}</a></code> is not yet complete.'),
              category='warning')
        return redirect(url_for('home'))

    return render_template('results.html', task=task)


if __name__ == '__main__':
    app.run(debug=True)
