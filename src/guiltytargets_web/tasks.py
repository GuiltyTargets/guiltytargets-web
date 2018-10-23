import os
import time

import click

from ppi_network_annotation.pipeline import generate_ppi_network
from ppi_network_annotation.model.attribute_network import AttributeNetwork
from ppi_network_annotation.model.labeled_network import LabeledNetwork
from guiltytargets.pipeline import rank_targets


def guiltytargets_pipeline(
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
    start_time = time.time()

    assert os.path.exists(ppi_graph_path), f'ppi graph file does not exist: {ppi_graph_path}'
    assert os.path.exists(dge_path), f'differential expression file does not exist: {dge_path}'
    os.makedirs(output_dir, exist_ok=True)

    click.secho('generating PPI network', color='cyan')
    network = generate_ppi_network(
        ppi_graph_path=ppi_graph_path,
        gene_expression_file_path=dge_path,
        maximum_adjusted_p_value=0.05,
        maximum_log2_fold_change=-1,
        minimum_log2_fold_change=1,
        entrez_id_header=entrez_id_header,
        log_fold_change_header=l2fc_header,
        adjusted_p_value_header=adjp_header,
        base_mean_header=base_mean_header,
        split_char=split_char,
        hippie_min_edge_weight=0,
    )
    labeled_network = LabeledNetwork(network)
    attribute_network = AttributeNetwork(network)

    rv = {
        'adjacency_list': network.get_adjlist(),
        'attribute_adjacency_list': attribute_network.get_attribute_mappings(),
        'label_mappings': labeled_network.get_index_labels(targets),
    }

    results_model = rank_targets(network=network, targets=targets, home_dir=output_dir)

    rv['results'] = results_model.to_json()
    rv['time'] = time.time() - start_time

    return rv
