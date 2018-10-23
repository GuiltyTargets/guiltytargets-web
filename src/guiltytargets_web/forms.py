# -*- coding: utf-8 -*-

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms.fields import RadioField, StringField, SubmitField, TextAreaField

PPI_PATH = '/Users/cthoyt/ownCloud/Gene-Prioritization-Data/MayoRNASeq-TCX/hippie_current.edgelist'

ppi_graph = RadioField(
    'PPI Graph',
    choices=[
        ('string', 'STRING'),  # TODO add link
        (PPI_PATH, 'HIPPIE'),
    ],
    default=PPI_PATH
)

class GuiltyTargetsForm(FlaskForm):
    """The form for using the GAT2VEC pipeline."""
    entrez_gene_identifiers = TextAreaField('Entrez Gene Identifiers')
    ppi_graph = ppi_graph
    file = FileField(
        'Differential Gene Expression File',
        # validators=[DataRequired()],
    )
    gene_symbol_column = StringField(
        'Gene Symbol Column Name',
        default='Gene.symbol',
    )
    log_fold_change_column = StringField(
        'Log Fold Change Column Name',
        default='logFC',
    )
    separator = RadioField(
        'Separator',
        choices=[
            ('\t', 'My document is a TSV file'),
            (',', 'My document is a CSV file'),
        ],
        default='\t')

    # Submit
    submit = SubmitField('Upload')
