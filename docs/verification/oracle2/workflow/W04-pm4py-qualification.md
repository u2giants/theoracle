# W04a qualification input — dependency not admitted

Exact stable PM4Py: **2.7.22**, upstream release commit `0715c31f3f1d85924107d6aa5329806db69df899`.
Source: https://github.com/process-intelligence-solutions/pm4py/releases/tag/2.7.22
License: https://github.com/process-intelligence-solutions/pm4py/blob/2.7.22/LICENSE
Inspected upstream source files: LICENSE, setup.py, requirements.txt, analysis.py, discovery.py, conformance.py; metadata came from the exact PyPI version, not a floating resolver.

The release uses AGPL-3.0. Oracle is intended to serve employees through a restricted authenticated web application and dedicated Python workers. This repository has no root LICENSE establishing a compatible distribution or network-user source offer. A separate analytical worker does not resolve license compatibility. No legal conclusion, source-offer commitment, license purchase, or publication is authorized by this memo.

Intended APIs (reviewed exact source): `convert_to_petri_net`, `check_soundness`, `discover_petri_net_inductive`, token replay fitness/conformance, BPMN/Petri utilities. Pure Oracle compilation preserves occurrence IDs; semantic completeness is independently checked before formal analysis. Supported XOR/AND loops only; unknown control semantics retain a partial map and cannot be analyzed.

PyPI wheel size: 2,498,290 bytes, excluding dependencies. Dependency tree includes numpy, pandas, networkx, graphviz, scipy, lxml, matplotlib, pytz, tqdm, wheel, setuptools and conditional cvxopt (Python <3.15). This is metadata, not a measured installed worker footprint. Resource qualification remains unperformed: initial limits 250 occurrences, 500 transitions, 50 gateways, 30 seconds and 512 MiB, cancellable in an isolated process.

Admission decision required from the assigned technical reviewer on exact deployment/license fit. Until that decision resolves compatibility, PM4Py installation, bundling and hosted deployment are denied. Documentary source preservation, typed compiler contract, log import and deterministic measured-event accounting can proceed. No substitute library removes the requested PM4Py capability. W04b stays open if fit cannot be established.

## Independent qualification outcome — October 11, 2026, 8:50 PM EDT

Muse, selected through the in-rotation `ai-review` process, returned **VERDICT: BLOCKED**. The review did not admit installation, bundling, deployment, or formal-analysis claims. Exact fit is unestablished: no compatible license/distribution basis or employee network-user source-offer commitment, no authorized purchase/legal determination, and no measured installed worker footprint or cancellable runtime qualification. Moving imports to another worker is explicitly insufficient. Documentary preservation, the pure compiler contract, operational imports and deterministic event accounting may proceed. The requested PM4Py capability remains open. The source-confidentiality business question was asked separately; an answer alone does not replace technical licensing qualification.

Report is private under `.ai/reviews/muse-oracle-operating-w04-qualification-20261012T004951Z-714972-14991.md`; its complete bytes and hash are retained in the session's protected review store. No private business source was supplied. No package was installed or replaced.

## Owner source-delivery decision — October 11, 2026 EDT

Albert answered the business question verbatim: "users may receive it under the library’s licensing terms". LICENSE, SOURCE_OFFER.md and THIRD_PARTY_NOTICES.md now record the compatible source-offer proposal. A clean-commit archive builder, authenticated download route and operating-model link are implemented; no private source or credentials are included. Deterministic archive and authenticated delivery tests gate the offer. This owner decision removes the source-confidentiality business blocker only. Exact W04a technical fit review continues in the same Muse conversation; PM4Py is not installed or bundled, W04b resource qualification remains open, and no hosted release is approved.
