"""Combine configuration layers."""


def merge_config(base: dict, override: dict) -> dict:
    base.update(override)
    return base
