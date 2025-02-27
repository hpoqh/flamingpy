# Copyright 2020 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for StablizerGraph classes in stab_graph.py.

The networkx implementation is used as a reference.
"""
import itertools as it

from numpy.random import default_rng
import pytest

from flamingpy.codes import alternating_polarity, Stabilizer, SurfaceCode
from flamingpy.cv.ops import CVLayer
from flamingpy.decoders.decoder import assign_weights, CV_decoder, GKP_binner
from flamingpy.decoders.mwpm.matching import NxMatchingGraph


# Test parameters

stab_graph_backend = ["retworkx"]

code_params = it.product(
    [2, 3, 4],
    ["open", "periodic"],
    ["primal", "dual"],
    [1, 0.1, 0.01],
    [0, 0.5, 1],
    stab_graph_backend,
)


@pytest.fixture(scope="module", params=code_params)
def enc_state(request):
    """Return the encoded state from compute_enc_state with one set of
    parameters."""
    return compute_enc_state(request)


def compute_enc_state(request):
    """RHGCode object and an encoded CVLayer with the networkx reference and
    another backend for use in this module."""
    distance, boundaries, ec, delta, p_swap, backend = request.param
    weight_options = {
        "method": "blueprint",
        "integer": True,
        "multiplier": 100,
        "delta": delta,
    }
    # Noise model
    cv_noise = {"noise": "grn", "delta": delta, "sampling_order": "initial"}
    seed = default_rng().integers(0, 2**32)

    # NX reference code
    nx_DVRHG = SurfaceCode(
        distance=distance,
        ec=ec,
        boundaries=boundaries,
        polarity=alternating_polarity,
        backend="networkx",
    )
    # CV (inner) code/state
    nx_CVRHG = CVLayer(nx_DVRHG, p_swap=p_swap)
    # Apply noise
    nx_CVRHG.apply_noise(cv_noise, default_rng(seed))
    # Measure syndrome
    nx_CVRHG.measure_hom("p", nx_DVRHG.all_syndrome_inds, rng=default_rng(seed))
    assign_weights(nx_DVRHG, "MWPM", **weight_options)
    CV_decoder(nx_DVRHG, translator=GKP_binner)

    print(f"rx + {ec}")
    # Comparison code
    DVRHG = SurfaceCode(
        distance=distance,
        ec=ec,
        boundaries=boundaries,
        polarity=alternating_polarity,
        backend=backend,
    )
    # CV (inner) code/state
    states = {"p": nx_CVRHG._states["p"]}
    CVRHG = CVLayer(DVRHG, states)
    # Apply noise
    CVRHG.apply_noise(cv_noise, default_rng(seed))
    # Measure syndrome
    CVRHG.measure_hom("p", DVRHG.all_syndrome_inds, rng=default_rng(seed))
    assign_weights(DVRHG, "MWPM", **weight_options)
    CV_decoder(DVRHG, translator=GKP_binner)

    return nx_DVRHG, nx_CVRHG, DVRHG, CVRHG


def convert_dict_of_weights(weights):
    """Convert RHGCubes into tuples of nodes and return a dictionary between
    them and path weights."""
    conversion = dict()
    for (n, w) in weights.items():
        if isinstance(n, Stabilizer):
            conversion[tuple(n.egraph.nodes())] = int(w)
        else:
            conversion[n] = int(w)
    return conversion


def assert_weights(w1, w2):
    """Assert that two tuple-to-weight dictionaries are equal."""
    assert convert_dict_of_weights(w1) == convert_dict_of_weights(w2)


def test_shortest_paths_have_same_weight(enc_state):
    """Test that different backends return shortest paths with the same
    weights.

    This also compare that the format are the same.
    """
    nx_code, code = enc_state[0], enc_state[2]
    for ec_str in nx_code.ec:

        nx_stab_graph = getattr(nx_code, ec_str + "_stab_graph")
        nx_stab_graph.assign_weights(nx_code)
        stab_graph = getattr(code, ec_str + "_stab_graph")
        stab_graph.assign_weights(code)

        # Starting from high
        nx_weights, _ = nx_stab_graph.shortest_paths_from_high()
        weights, _ = stab_graph.shortest_paths_from_high()
        assert_weights(nx_weights, weights)

        # Starting from low
        nx_weights, _ = nx_stab_graph.shortest_paths_from_low()
        weights, _ = stab_graph.shortest_paths_from_low()
        assert_weights(nx_weights, weights)

        # Starting from real nodes
        for (nx_source, source) in zip(nx_stab_graph.real_nodes(), stab_graph.real_nodes()):
            nx_weights, _ = nx_stab_graph.shortest_paths_without_high_low(nx_source)
            weights, _ = stab_graph.shortest_paths_without_high_low(source)
            assert_weights(nx_weights, weights)


code_params2 = it.product(
    [3, 4], ["open", "periodic"], ["primal", "dual"], [1, 0.9], [0, 0.5, 1], stab_graph_backend
)
# An RHGCode object as well as an encoded CVLayer for use in this module.
@pytest.fixture(scope="module", params=code_params2)
def enc_state2(request):
    """The encoded state from compute_enc_state with another set of
    parameters."""
    return compute_enc_state(request)


def test_similar_matching_are_generated(enc_state2):
    """Test that different backends yield the matching with same weight.

    Use the NxMatchingGraph as a target.
    """
    nx_code, code = enc_state2[0], enc_state2[2]
    for ec in nx_code.ec:
        matching_graph_from_nx = NxMatchingGraph(ec, nx_code)
        matching_from_nx = matching_graph_from_nx.min_weight_perfect_matching()
        weights_from_nx = matching_graph_from_nx.total_weight_of(matching_from_nx)

        matching_graph = NxMatchingGraph(ec, code)
        matching = matching_graph.min_weight_perfect_matching()
        weights = matching_graph.total_weight_of(matching)

    assert weights == weights_from_nx
