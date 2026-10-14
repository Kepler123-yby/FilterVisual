"""Explicit model factories, without hidden truth initialization."""
from __future__ import annotations

from filtervisual.models.rm_cv import RoboMasterCVModel


def make_model(definition, geometry):
    if definition.kind == "python":
        # Added by the local custom-model module without duplicating the engines.
        from filtervisual.models.custom import load_model
        return load_model(definition.source, definition.params, geometry)
    if definition.kind != "builtin":
        raise ValueError(f"unsupported model kind: {definition.kind}")
    if definition.builtin_name not in ("rm_cv", "robomaster_cv"):
        raise ValueError(f"unknown builtin model: {definition.builtin_name}")
    return RoboMasterCVModel(geometry, **definition.params)


def make_filter(config, model, models=None):
    from filtervisual.filters.protocol import make_filter as factory
    return factory(config, model, models=models)
