# W04 qualification record — local optional integration admitted

Exact stable PM4Py: **2.7.22**, upstream release commit `0715c31f3f1d85924107d6aa5329806db69df899`.
Source: https://github.com/process-intelligence-solutions/pm4py/releases/tag/2.7.22
License: https://github.com/process-intelligence-solutions/pm4py/blob/2.7.22/LICENSE
Inspected upstream source files: LICENSE, setup.py, requirements.txt, analysis.py, discovery.py, conformance.py; metadata came from the exact PyPI version, not a floating resolver.

The release uses AGPL-3.0. Oracle is intended to serve employees through a restricted authenticated web application and dedicated Python workers. Historical pre-decision finding: at the initial inspection, this repository had no root LICENSE establishing a compatible distribution or network-user source offer. A separate analytical worker does not resolve license compatibility. This historical finding predates the owner source-delivery decision recorded below. No legal conclusion, license purchase or public publication is authorized.

Intended APIs (reviewed exact source): `convert_to_petri_net`, `check_soundness`, `discover_petri_net_inductive`, token replay fitness/conformance, BPMN/Petri utilities. Pure Oracle compilation preserves occurrence IDs; semantic completeness is independently checked before formal analysis. Supported XOR/AND loops only; unknown control semantics retain a partial map and cannot be analyzed.

PyPI wheel size: 2,498,290 bytes, excluding dependencies. Dependency tree includes numpy, pandas, networkx, graphviz, scipy, lxml, matplotlib, pytz, tqdm, wheel, setuptools and conditional cvxopt (Python <3.15). This is metadata, not a measured installed worker footprint. The initial, pre-measurement qualification proposed limits 250 occurrences, 500 transitions, 50 gateways, 30 seconds and 512 MiB, cancellable in an isolated process.

Admission decision required from the assigned technical reviewer on exact deployment/license fit. The initial pre-decision gate denied installation, bundling and hosted deployment; later scoped verdicts below supersede only the specifically admitted actions. Documentary source preservation, typed compiler contract, log import and deterministic measured-event accounting can proceed. No substitute library removes the requested PM4Py capability. W04b stays open if fit cannot be established.

## Independent qualification outcome — October 11, 2026, 8:50 PM EDT

Muse, selected through the in-rotation `ai-review` process, returned **VERDICT: BLOCKED**. The review did not admit installation, bundling, deployment, or formal-analysis claims. Exact fit is unestablished: no compatible license/distribution basis or employee network-user source-offer commitment, no authorized purchase/legal determination, and no measured installed worker footprint or cancellable runtime qualification. Moving imports to another worker is explicitly insufficient. Documentary preservation, the pure compiler contract, operational imports and deterministic event accounting may proceed. The requested PM4Py capability remains open. The source-confidentiality business question was asked separately; an answer alone does not replace technical licensing qualification.

Report is private under `.ai/reviews/muse-oracle-operating-w04-qualification-20261012T004951Z-714972-14991.md`; its complete bytes and hash are retained in the session's protected review store. No private business source was supplied. No package was installed or replaced.

## Owner source-delivery decision — October 11, 2026 EDT

Albert answered the business question verbatim: "users may receive it under the library’s licensing terms". LICENSE, SOURCE_OFFER.md and THIRD_PARTY_NOTICES.md now record the compatible source-offer proposal. A clean-commit archive builder, authenticated download route and operating-model link are implemented; no private source or credentials are included. Deterministic archive and authenticated delivery tests gate the offer. This owner decision removes the source-confidentiality business blocker only. Exact W04a technical fit review continues in the same Muse conversation; PM4Py is not installed or bundled, W04b resource qualification remains open, and no hosted release is approved.

## Scoped independent approval and isolated measurement — October 11, 2026 EDT

Muse returned APPROVE at exact 9cb7bc8701316a8e0b2d3c71480c0c11cbc88194, only for W04a fit and an isolated, pinned measurement environment. Worker bundling, hosted release, resource-fit claims and adapter enablement remained closed. The report hash is recorded in W04-measurement.json. The authenticated browser subsequently passed download/hash/revision checks and anonymous/post-logout denial at that exact head.

The hash-pinned isolated environment exercised PM4Py 2.7.22: a 250-step/500-arc linear net passed soundness, discovery and replay within 2.65 seconds and 177 MB peak RSS. The compiler-backed XOR/AND/rework-language and deadlock probes passed. A 250-step/50-gateway parallel fixture exhausted the enforced 512 MiB address-space bound and remained incomplete with its original map unchanged; this is not a successful formal result or a smaller-limit substitution. Its measured peak RSS was 209 MB. The separate real subprocess tests prove timeout and memory-exhaustion preservation. No company facts were analyzed and no product qualification flag was enabled.

The offered archive now includes the exact SHA256-pinned PM4Py source distribution plus complete notices and exact source URLs/hashes for all 22 measured dependencies. The descriptor/notice inventory and isolated measurement lock are source-delivery inputs, not product installation/bundle admission. They require fresh exact-input review and authenticated delivery proof before any further installation or analytics enablement.


## Local integration admission and remaining solver qualification — October 11, 2026 EDT

Muse report 20261012T013939Z-1382544-17881 approved the local hash-pinned optional extra and worker-bundle tests only at b0be2b23cf82cd9552b6c37e46d8d5867b6ae48b. Neither default-worker installation, deployment, product enablement nor runtime qualification flags were admitted. The browser passed authenticated source delivery, exact archive hash/revision, anonymous denial and logout denial at that exact head.

The timing records describe different probes: the 250-step linear-net run took 2.645 elapsed / 2.366 CPU seconds; the compiler-language/large-parallel fixture record took 0.86 elapsed / 0.934 CPU seconds and ended incomplete on the parallel fixture. They must not be compared as the same execution. Neither establishes private company coverage.

The optional extra now exercises the real bounded adapter: XOR, AND, rework, deadlock, preserved large-fixture exhaustion, discovery, shuffled-case conformance, and public admission denial. The installed exact API returns mixed enum/string diagnostic keys; those are normalized to stable text. The original map is preserved on exhaustion. A separate native-child timeout test proves descendant cancellation in the worker's exclusively owned process group. CI includes these mandatory tests with the optional extra; default worker requirements remain free of PM4Py.

Actual Woflan execution warns that the SciPy solution may be unstable and recommends PuLP. This warning is not suppressed; formal reliability remains unaccepted. Exact PuLP/CBCbox source, license, compatibility, source delivery and bounded native-child execution are under the same independent qualification conversation. No solver has been installed and no product qualification flag is enabled. Private-source semantic acceptance and hosted proof remain open.


## Isolated solver compatibility and cancellation — October 11, 2026 EDT

Muse's scoped approval at cfd78809c2c4d42eea0ff6b493eb6929d835cdcb admitted only isolated PuLP 4.0.0/CBCbox measurement. The experiment failed at the PM4Py import: PuLP 4 removed LpStatus required by PM4Py 2.7.22. It is not a compatible release candidate; the failed environment was not installed into a product worker.

The fresh scoped approval at 87392ad25418f4279100039184c04488c7758431 admitted only replacing that disposable experiment with PuLP 3.3.0. Its exact source distribution SHA256 is 7eb99b9ce7beeb8bbb7ea9d1c919f02f003ab7867e0d1e322f2f2c26dd31c8ba (16,301,847 bytes). Actual XOR, AND, loop and deadlock fixtures passed; the 250-step/50-gateway/324-edge parallel fixture returned sound within the unchanged 512 MiB address-space / 30 CPU-second limits. Elapsed time was 2.822 seconds, CPU 2.617 seconds, peak RSS 195,903,488 bytes. SciPy instability warnings were absent without filtering. This is synthetic structure proof only.

The bundled Linux solver reports CBC 2.10.3, built December 15, 2019; binary SHA256 is 2e17077752aa52b06385ad248c9e90bb4f1ce34038c34c94e1012ca6adea5cc7. Its actual native descendant was terminated after 2.006 seconds in the exclusively owned worker process group; the original map survived. PuLP's MIT notice and bundled CBC EPL-1.0 notice were inspected. Matching corresponding source and complete binary dependency/build inventory remain unqualified; the PuLP archive alone is not claimed to provide them. Its source archive also exceeds the current single-response hosted download limit. Bounded authenticated delivery needs implementation and verification before this solver can be proposed for bundling.

No PuLP/CBC product dependency, default worker bundle, hosted release, analytical qualification flag, company generation, or actual-data acceptance is admitted by these reports. The 125-case mandatory synthetic suite passed with zero skips after the source/assembly/retrieval and diagnosed-correction changes; this does not close independent private semantic or hosted acceptance.
