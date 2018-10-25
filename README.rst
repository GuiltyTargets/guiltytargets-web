GuiltyTargets-Web
=================
Running Locally
---------------
1. Clone this repository with:

.. code-block:: bash

   $ git clone https://github.com/guiltytargets/guiltytargets-web.git
   $ cd guiltytargets-web

2. Run RabbitMQ. On Mac, this is easy with homebrew

.. code-block:: bash

   $ # if you need to install rabbitmq, use the first command
   $ brew install rabbitmq
   $ brew services start rabbitmq

3. Run the web server using ``pipenv``:

.. code-block:: bash

   $ pipenv run gunicorn -b 0.0.0.0:5000 wsgi:app

4. Run the Celery worker using ``pipenv``:

.. code-block:: bash

   $ pipenv run celery worker -A wsgi.celery -l INFO

See the module docstring of ``wsgi.py`` for similar instructions.

Running with Docker
-------------------
After cloning this repository and ``cd``ing into it, run:

.. code-block:: bash

   $ docker-compose up
