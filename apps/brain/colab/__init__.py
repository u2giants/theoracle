"""Headless Google Colab GPU orchestration, batch runner, and QLoRA tools (#664).

Modules in this package run either on an operator/CI host (``preflight``) or
inside an ephemeral Colab GPU runtime (``run_vllm_batch``, ``train_relations_lora``,
``drain_leases``). Production ``apps/brain`` never imports GPU libraries.
"""
