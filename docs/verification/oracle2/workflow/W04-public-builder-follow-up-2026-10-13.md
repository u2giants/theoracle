# W04 public builder/distributor follow-up

Read-only primary-source investigation on October 13, 2026 EDT at Oracle source
`a6cdd5b6a8c9074d22292d4d3e474de36338228e`. This is research, not analytical
product admission, a license opinion, a source delivery receipt, or live proof.
All six unchanged PuLP 3.3.0 binaries and seven notices remain preserved.
No binary execution, package installation, private reading, credentials,
provider call, upstream message, or external write occurred.

## Fresh primary evidence

- [PuLP PR426](https://github.com/coin-or/pulp/pull/426) attributes its update to
  AMPL downloads. That establishes distributor history, not an exact original
  build input manifest for the current Windows32 CBC2.9.7 binary.
- [AMPL v20191215 release API](https://api.github.com/repos/ampl/coin/releases/tags/v20191215)
  freshly lists four binary archives: coin-linux32.tar.gz 13,765,715 bytes;
  coin-linux64.tar.gz 14,795,730; coin-osx.tar.gz 14,121,771; coin-win64.zip
  8,884,776. There is no Windows32 binary asset in that release. The release
  page's six assets include two automatically generated source archives.
- [Exact AMPL build recipe](https://raw.githubusercontent.com/ampl/coin/653364bb6c9e742fbb1e90522ca50890b8355b20/azure-pipelines.yml)
  selects mutable manylinux container tags, updates submodules with `--remote`,
  and comments out the Windows32 matrix. The checked-in gitlink and source
  recipes therefore do not establish the actual historical mp checkout,
  image digest, or compiler/runtime inputs. Source inspection cannot recover
  an absent actual-build receipt by choosing nearby versions.
- [Original ARM builder recipe](https://github.com/coin-or/pulp/issues/672#issuecomment-1735615234)
  uses python:3.11.3-bullseye, apt gfortran, coinbrew master and a static Cbc
  build without an immutable Cbc/dependency selector. This recipe exists;
  its missing historical input pins remain unknown.
- [Immutable Cbc2.10.10 dependency declarations](https://raw.githubusercontent.com/coin-or/Cbc/133f1171f1667c930e46efd350f4be8ad995b231/.coin-or/Dependencies)
  use stable branches for CoinUtils/Osi/Clp/Cgl and optional wrappers. They
  do not identify the historical ARM build's selected dependency commits.

## Exact remaining qualification boundary

The existing [six-platform provenance packet](W04-cbc-source-provenance.md)
remains the byte/hash/source inventory. Linux32/Linux64/macOS64 byte matches,
Windows64 timestamp-only differences, available CBC version source archives,
ARM recipe, and preserved inconsistent license texts are not discarded.

Remaining unknowns are Windows32 exact binary-to-build/dependency association;
ARM exact source/dependency/container/runtime inputs; historical AMPL actual
mp/container/runtime choices; and complete linked notice/source coverage.
Only actual builders/distributors can authenticate unavailable historical
choices if the acceptance requirement needs that association. No contact was
authorized or sent. Missing signed/reproducible-build attestation is not itself
a finding that a license requirement is violated. The coordinator and assigned
reviewer determine the actual qualification requirement from the honest packet.

The current source-offer builder adds one pinned PM4Py source archive, not the
complete CBC/PuLP/source population. Existing authenticated chunk transport
does not by itself prove complete product-bound delivery. Intact AMPL source
(52,745,543 bytes), PuLP source (16,301,847 bytes), and mp source (1,396,530 bytes)
already total 70,443,920 bytes before additional relevant archives, exceeding
the existing single 64 MiB artifact bound. Preserve complete originals;
qualified multipart delivery and exact product revision binding remain open.
No binary removal, vendor substitution, flag enablement, or bundle approval
is proposed by this evidence.
