# -*- coding: utf-8 -*-

"""Forms for GuiltyTargets-Web."""

import os

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms.fields import RadioField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired

HERE = os.path.abspath(os.path.dirname(__file__))

STRING_PATH = os.path.join(os.pardir, os.pardir, 'data', 'string.edgelist')
HIPPIE_PATH = os.path.join(os.pardir, os.pardir, 'data', 'hippie.edgelist')


class Form(FlaskForm):
    """The form for using the GuiltyTargets pipeline."""

    entrez_gene_identifiers = TextAreaField(
        'Entrez Gene Identifiers',
        validators=[DataRequired()],
    )

    ppi_graph = RadioField(
        'PPI Graph',
        choices=[
            (STRING_PATH, 'STRING'),
            (HIPPIE_PATH, 'HIPPIE'),
        ],
        default=HIPPIE_PATH,
    )

    file = FileField(
        'Differential Gene Expression File',
        validators=[DataRequired()],
    )

    gene_symbol_column = StringField(
        'Gene Symbol Column Name',
        default='Gene.symbol',
        validators=[DataRequired()],
    )

    log_fold_change_column = StringField(
        'Log Fold Change Column Name',
        default='logFC',
        validators=[DataRequired()],
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
