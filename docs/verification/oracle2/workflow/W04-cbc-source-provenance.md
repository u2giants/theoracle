# W04 CBC unchanged-distribution public provenance packet

This public-only record preserves primary source associations and unknown historical inputs for all six unchanged PuLP 3.3.0 binaries. It is an inventory and review input, not library admission, a complete corresponding-source determination, source-offer delivery, or a license opinion. No binary was executed or altered.

The later qualification and follow-up supersede earlier provisional statements: all four Windows64 differences are timestamp metadata; the ARM author recipe exists but its historical dependency inputs are unpinned.

## Exact relationship summary and missing closure

| Binary | Established relationship | Exact historical evidence still missing |
|---|---|---|
| Linux32 | Byte-identical AMPL v20191215 CBC2.10.3 release | Actual remote mp checkout, mutable build image/runtime qualification |
| Linux64 | Byte-identical AMPL v20191215 CBC2.10.3 release | Actual remote mp checkout, mutable build image/runtime qualification |
| macOS64 | Byte-identical AMPL v20191215 CBC2.10.3 release | Actual remote mp checkout and historical build/runtime qualification |
| Windows64 | PuLP PR426 bytes; AMPL release differs only at two repeated PE timestamp fields | Signed historical build association and actual dependency/runtime input record |
| Windows32 | PuLP PR426 bytes identify CBC2.9.7; matching version monolithic source available | MISSING exact original binary-to-build/source/dependency association; no matching AMPL win32 release asset |
| ARM64 | PuLP PR685 bytes identify CBC2.10.10; author native Debian recipe and immutable CBC tag available | MISSING historical Docker digest, coinbrew/CBC/dependency commits and runtime inputs; differing license texts remain preserved |

All six adjacent notices and the PuLP root notice remain intact. Sources for a version do not prove exact custom binary dependency closure. No binary population is removed to avoid an unresolved obligation.

## Retained primary research

Verified October 11, 2026, 11:28 PM EDT. No solver execution, build, installation, vendor edits, provider dispatch, or private-source reading performed. Public archives were inspected in memory without filesystem extraction.

## Exact binary established

PuLP upstream PR426: https://github.com/coin-or/pulp/pull/426
Merge commit: 216d1e678a63f1da4208e4a525f8d0bea9437566
Primary binary URL: https://raw.githubusercontent.com/coin-or/pulp/216d1e678a63f1da4208e4a525f8d0bea9437566/pulp/solverdir/cbc/linux/64/cbc
Downloaded binary: 7,178,823 bytes; SHA256 2e17077752aa52b06385ad248c9e90bb4f1ce34038c34c94e1012ca6adea5cc7. Exact match to requested PuLP3.3.0 binary.

AMPL upstream release: https://github.com/ampl/coin/releases/tag/v20191215
Tag resolves to commit 653364bb6c9e742fbb1e90522ca50890b8355b20.
Primary asset: https://github.com/ampl/coin/releases/download/v20191215/coin-linux64.tar.gz
Archive: 14,795,730 bytes; SHA256 ee7f6cb43d4b1ad18ae29546ee097c34a32d70111b81bb206856b56b2c730486.
Contained root cbc: 7,178,823 bytes; SAME exact SHA256 above. Thus release provenance is established by bytes, rather than inferred from version/date.
Archive coin-versions.txt identifies CBC2.10.3, driver20130502, ASL20161228.
Archive coin-license.txt: 11,415 bytes; SHA256 0076749b626931ea5aaee25ddd5019fbfd96da78243cc0d5bd24fe246500981f; Eclipse Public License version1.0.

## Matching release source and build scripts available

Exact AMPL release source: https://codeload.github.com/ampl/coin/tar.gz/653364bb6c9e742fbb1e90522ca50890b8355b20
Complete archive: 52,745,543 bytes; SHA256 1e22803be8d73ce8529228cd8867404cb88a90cd45baab1020fc8debc98231f9; 13,799 members parsed through gzip EOF. An initial 50MiB bounded read was incomplete and was overwritten by this complete archive; its digest must not be used.

configure.ac inside Cbc component tree establishes:
CBC2.10.3, CoinUtils2.11.2, Osi0.108.4, Clp1.17.3, Cgl0.60.2.
Each component LICENSE is EPL1.0, identical SHA256 0076749b626931ea5aaee25ddd5019fbfd96da78243cc0d5bd24fe246500981f.

Independent primary monolithic component source package:
https://www.coin-or.org/download/source/Cbc/Cbc-2.10.3.tgz
13,677,619 bytes; SHA256 ad388357129497c1cc3be50c3707b1995fddf0a4188abc8e3669173f0179ecff.
Contains the same five configure.ac version declarations and EPL1.0 component LICENSE files. This upstream tarball alone omits AMPL top-level build modifications and mp submodule, so use complete AMPL source plus mp for a release source packet.

Build files present at exact release commit:
https://github.com/ampl/coin/blob/653364bb6c9e742fbb1e90522ca50890b8355b20/CMakeLists.txt
https://github.com/ampl/coin/blob/653364bb6c9e742fbb1e90522ca50890b8355b20/azure-pipelines.yml
https://github.com/ampl/coin/blob/653364bb6c9e742fbb1e90522ca50890b8355b20/manylinux/build.sh
https://github.com/ampl/coin/blob/653364bb6c9e742fbb1e90522ca50890b8355b20/manylinux/create.sh
https://github.com/ampl/coin/blob/653364bb6c9e742fbb1e90522ca50890b8355b20/manylinux/bootstrap.sh

Linux CI selects fdabrandao/manylinux64:coin_cmake-3.12.4, runs CMake, builds all/coin-versions, packages CBC and license. Top-level CMake defines static-library selection machinery and the ASL integration.

## ASL source and license

.gitmodules points ThirdParty/mp to https://github.com/ampl/mp.git.
Exact release tree gitlink: 51aeb2c386342ed4f48cc78d3df9e4e57a70f667.
https://codeload.github.com/ampl/mp/tar.gz/51aeb2c386342ed4f48cc78d3df9e4e57a70f667
1,396,530 bytes; SHA256 4038a2d7fd698920049c29816b635cb79b9a373fe0bf2bf9f8ddaed2892c7833.
src/asl/solvers/asldate.c contains ASLdate_ASL=20161228, matching exact release artifact versions.
LICENSE.rst: 2,811 bytes; SHA256 2383d4f3f73e1399b8423d5477847e618624e994745df033dcb54ca416d7b19f; Lucent permissive notices and additional listed notices must be preserved in full, not relabeled EPL.
The mp commit is the most recent commit returned by primary GitHub history before release commit time; this supports matching gitlink. It is source evidence, not a reproducible-build attestation.

## Remaining uncertainty for root/reviewer decision

Exact CBC/CoinUtils/Osi/Clp/Cgl source versions and complete release source/build recipes are now available. No component-source absence was found.

CI verbatim: git submodule update --init --recursive --remote
Therefore gitlink alone does not prove the historical build checked out that same mp commit. The matching ASL date and last pre-release mp commit support it, but no signed build attestation or recorded actual submodule checkout was found in inspected primary records.

The historical build image is named by mutable tag, without an image digest in the source recipe. Exact compiler/container reconstruction remains unproven. CBC bytes contain GCC identity strings for Red Hat GCC4.1.2-55 and4.8.2-15. These indicate additional runtime/link provenance to inspect if corresponding-source requirements include those linked libraries; do not invent exact compiler-source closure.

No legal compatibility conclusion, product redistribution approval, artifact vendoring admission, complete license review, reproducible build, or hosted qualification is asserted here. Root owns those decisions. The exact public source archive is about52.7MB and will need corresponding-source delivery bounds that accommodate it plus mp if admitted.

## All-platform PuLP3.3.0 distribution inventory — correction/extension

PyPI source SHA2567eb99b9ce7beeb8bbb7ea9d1c919f02f003ab7867e0d1e322f2f2c26dd31c8ba; 16,301,847 bytes. Wheel SHA256dd6ad2d63f196d1254eddf9dcff5cd224912c1f046120cb7c143c5b0eda63fae; 16,387,700 bytes. Authoritative metadata: https://pypi.org/pypi/PuLP/3.3.0/json

Wheel and sdist contain SIX byte-identical CBC binaries and byte-identical adjacent notices:
- pulp-3.3.0/pulp/solverdir/cbc/linux/arm64/cbc: 7678656 bytes, SHA25690e1ee27a969cb2f54a02a2edbe8b1f5e4ba8e2b293e44584d96dbc750ba559b
- pulp-3.3.0/pulp/solverdir/cbc/linux/i32/cbc: 6593038 bytes, SHA25662911eb74138f5c9b74876f03db6209d8443a9042483343059b57678892ac7c2
- pulp-3.3.0/pulp/solverdir/cbc/linux/i64/cbc: 7178823 bytes, SHA2562e17077752aa52b06385ad248c9e90bb4f1ce34038c34c94e1012ca6adea5cc7
- pulp-3.3.0/pulp/solverdir/cbc/osx/i64/cbc: 6621848 bytes, SHA2569eeb33c515945620d89dfc2efef9c6740b559e14a6603153a156c6e288a5765b
- pulp-3.3.0/pulp/solverdir/cbc/win/i32/cbc.exe: 3588096 bytes, SHA2567d930a6301cf0f0da0d7fdfa94f49d31aec00d6dfde6097e01dbf004111e4fdb
- pulp-3.3.0/pulp/solverdir/cbc/win/i64/cbc.exe: 4388352 bytes, SHA256fb4642eca630f6263c365975aca7e87917cbe82ed7e6ccb79804e2f1f812419c

Linux i32, Linux i64 and macOS i64 exactly match binary bytes in AMPLv20191215 release assets. Corresponding AMPL CBC2.10.3 component sources/build recipes discussed above apply to those known release identities, subject to previous build-attestation caveats.

Windows i64 matches PuLP PR426 binary but differs from AMPLv20191215 win64 asset in exactly four bytes at offsets296,297,4013828,4013829. Release asset CBC hash6d0d5246c2c923be7556cf2be4328a45f7618954f4f2e56832d440a1fbd94f67; PuLP binary hashfb4642eca630f6263c365975aca7e87917cbe82ed7e6ccb79804e2f1f812419c. Same length and version2.10.3. PE timestamp bytes differ at296/297; The later qualification below establishes both repeated fields as timestamps. No byte identity or signed historical build attestation is claimed.

Windows i32 is CBC2.9.7, with embedded build date Nov24 2015 and PE timestamp corroboration. It matches PuLP PR426 checked-in bytes, but AMPLv20191215 has NO win32 asset. No exact matching source/build/dependency closure for this binary was found. PuLP PR426 generic description must not override the binary's actual version evidence.

Linux arm64 is CBC2.10.10, with embedded build date Sep26 2023 and GCC(Debian10.2.1-6)10.2.1 identity. Added by upstream PR685 / merge2b6b5fa6cdeef82fc8fd8f56aa2922f80b31d7a2:
https://github.com/coin-or/pulp/pull/685
That change adds the binary/notice/selection code; the original author recipe is recovered below, with immutable historical inputs still missing. Exact CoinUtils/Osi/Clp/Cgl linked versions, build flags and source checkout remain unproven. Do not use CBC2.10.3 sources for this binary.

Every adjacent coin-license.txt is EPL1.0 text. Linux/arm64/i32/i64, macOSi64, Windowsi32 all have 11,415-byte LF file SHA2560076749b626931ea5aaee25ddd5019fbfd96da78243cc0d5bd24fe246500981f. Windowsi64 has 11,654-byte CRLF notice SHA256b2cd389435fc11009fae20d53c4b1fdea53dab785b02aa4681d36af02b1a7ace. PuLP root LICENSE is MIT,1,127 bytes SHA256b41bca287571c8ac88dc634f7ccbad0910f5fe42e38fefe1304c3c3b85b94aec. Adjacent EPL notice presence is not proof of all linked third-party notice/source coverage, especially ASL and compiler runtimes.

## AMPL archive composition and system-library facts

The full AMPLsource archive is52,745,543 compressed bytes and contains13,799 entries. Uncompressed top-level source totals: Cbc50,061,632; Bonmin56,962,768; Couenne61,086,432; Ipopt17,478,238; ThirdParty66,271,876 bytes, plus root build files. It includes many unrelated/duplicated component trees. Read-only signature scan found no ELF/MZ member. It is not a minimal CBC-only packet; any reviewed repackaging must preserve the exact relevant source/build/license population and retain originalarchive hash/provenance. Source-only subset might fit smaller delivery bounds, but this research does not prescribe or authorize vendor modifications.

Primary license texts, facts only:
https://www.eclipse.org/legal/epl-v10.html — section3 gives conditions for object-code distribution and source availability. Full notices should be retained and assessed by assigned reviewer.
https://www.gnu.org/licenses/gpl-3.0.html — section1 defines System Libraries and excludes qualifying System Libraries from Corresponding Source. That is a defined conditional exclusion, not a blanket exclusion for every native library; whether it applies here is unestablished.
https://www.gnu.org/licenses/gcc-exception-3.1.html — GCC Runtime Library Exception gives conditional additional permission for target-code combinations resulting from Eligible Compilation Processes. Existence of that exception does not prove this historical binary's runtime versions, source or eligibility; those remain separate facts to qualify.

Unresolved all-distribution source coverage: Windowsi32 CBC2.9.7 exact build/dependency source; ARM64 CBC2.10.10 exact build/dependency source; Windowsi64 timestamp-only difference, with signed historical build attestation unproven; actual historic mp checkout; mutable historical image/runtime identity; complete notice coverage for linked third-party/runtime portions. None is resolved by the successful active-Linuxi64 soundness probe. Whole unchanged PuLP3.3.0 source/wheel distribution admission remains root/reviewer work.


GNU website fetch timed out during this pass. The stated conditional definitions were independently verified from GCC upstream release4.8.2 primary repository texts:
https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-4.8.2/COPYING3
https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-4.8.2/COPYING.RUNTIME
These upstream texts do not establish the exact Red Hat compiler patch/runtimes incorporated in the binary.

## Follow-up qualification: exact Windows delta and recoverable ARM recipe

Windowsi64 four-byte differences are now fully located in PE metadata, without executing either binary. PE COFF header starts288; its TimeDateStamp field is offset296. IMAGE_DEBUG_DIRECTORY resides at raw file offset4013824 and its TimeDateStamp field is offset4013828. The four differing bytes are only the low two bytes of each repeated timestamp: AMPL[120,143] vs PuLP[81,154]. All remaining4,388,348 bytes are identical. This establishes a timestamp-only byte delta, not a code/data difference. It does not assert a historical signed build attestation.

ARM original binary author posted a reproducible-style procedure:
https://github.com/coin-or/pulp/issues/672#issuecomment-1735615234
Docker base python:3.11.3-bullseye; install gfortran; retrieve coinbrew from its master branch; build Cbc with static linking and aarch64 build target. The author describes this as the working build and follows by copying dist/bin/cbc into PuLP. This recovers an original build recipe; it does NOT recover immutable Docker digest, coinbrew commit, Cbc commit or exact dependency commits because those inputs were mutable/unpinned. Avoid saying no recipe exists; precise unresolved item is exact historical input resolution.

CBC2.10.10 immutable source tag resolves133f1171f1667c930e46efd350f4be8ad995b231:
https://github.com/coin-or/Cbc/tree/133f1171f1667c930e46efd350f4be8ad995b231
https://codeload.github.com/coin-or/Cbc/tar.gz/133f1171f1667c930e46efd350f4be8ad995b231
Complete archive1,672,608 bytes; SHA2567495ba584de2d43c59abc6ef995c8f3bec29e7097f415613302dcd06733df66b.
.coin-or/Dependencies references CoinUtils stable/2.11, Osi stable/0.108, Clp stable/1.17, Cgl stable/0.60 and optional ThirdParty wrappers. These are branches, not immutable dependency versions, and do not prove which source the unpinned ARM build selected.
License inconsistency to preserve for assigned reviewer: release root LICENSE is EPL2.0 (13,673 bytes SHA2565af94e656b0a51f0694901e8ee715dfb738ab65b88e8e2b9c52fa80340fa1500); .coin-or/config.yml declares EPL2.0; nested Cbc/LICENSE remains EPL1.0 (same11,415-byte SHA2560076749b...); PuLP ARM adjacent notice remains EPL1.0. Do not silently normalize or claim license fit.
Official CBC2.10.10 release asset list has Windows/macOS/x86_64Linux artifacts but no ARM asset matching PuLP's custom build. Official CBC2.9.7 releases API returns404, despite its valid source tag.

Windowsi32 official corresponding VERSION source is available:
https://www.coin-or.org/download/source/Cbc/Cbc-2.9.7.tgz
Complete archive13,676,503 bytes; SHA256637d080d381e620888d032cba28a3f1f8199f3b5619a3b763aa1470fda543817.
configure.ac versions: CBC2.9.7, CoinUtils2.10.11, Cgl0.59.7, Clp1.16.9, Osi0.107.6.
Immutable CBC2.9.7 Git tag resolvesa10ce900aa0bc31d8f873d66dd93df120229b77c:
https://github.com/coin-or/Cbc/tree/a10ce900aa0bc31d8f873d66dd93df120229b77c
The monolithic version archive supplies all those component sources and build-system scripts. Exact bundle binary/source association is UNKNOWN because no matching upstream win32 binary release or its build inputs were found. The downloaded monolithic archive must not be claimed as proven exact linked source solely because CBC's top-level version matches.

Updated residual list: ARM exact dependency/runtime input resolution and license-text inconsistency; Windowsi32 exact binary-to-build/source association; historical AMPL mp/image/runtime qualification. Windowsi64 unexplained four-byte delta is resolved as timestamp-only metadata and should no longer be listed as unexplained code variation. No product bundle is enabled by this research.

## Fresh public follow-up

Verified October 12, 2026, 01:05 PM EDT

# PuLP 3.3.0 unchanged distribution follow-up

Public, read-only research. No binary execution, vendor modifications, credentials, private originals, or paid application requests. Existing six-binary memo remains authoritative for byte hashes and recovered sources. This note narrows, rather than expands, the unresolved evidence.

## Fresh primary facts

- PuLP Win32 file history: https://api.github.com/repos/coin-or/pulp/commits?path=src/pulp/solverdir/cbc/win/32/cbc.exe and https://api.github.com/repos/coin-or/pulp/commits?path=pulp/solverdir/cbc/win/32/cbc.exe. Initial commit 658c96bbe6d24b9689ee25fbf229388b1fc65ae7 added a DIFFERENT 3,591,168-byte binary (SHA256 107dd72d0a1eaf29ad871c6b60d83bf5980b956ab7eaaf91fe4bf8cfd7971788). Thus the initial 2015 build cannot establish provenance for the current 3,588,096-byte CBC2.9.7 binary. Current bytes entered through PR426, whose own commit describes retrieval from AMPL. That source establishes distributor provenance, not the original build input manifest.
- Current AMPL primary releases inventory https://api.github.com/repos/ampl/coin/releases has v20191215 with four assets (linux32/linux64/osx/win64), and v20170826/20150122/v20140620 with no assets. No published matching win32 release asset is available through this inventory. Older tags are source records, not evidence of an exact matching Windows build.
- ARM original author recipe: https://github.com/coin-or/pulp/issues/672#issuecomment-1735615234. Exact recipe selects python:3.11.3-bullseye, apt gfortran, coinbrew master, and `coinbrew build Cbc --static --build=aarch64-unknown-linux-gnu --no-prompt`. No Cbc/version argument or dependency commit manifest appears. The author discusses failed Ubuntu experiments; the posted successful recipe is Debian Bullseye. Do not label this exact recipe Ubuntu.
- ARM author confirms native ARM environment, not cross-compilation: https://github.com/coin-or/pulp/issues/672#issuecomment-1743018476. No immutable input manifest is supplied in that comment.
- Read-only wheel ELF section inspection finds ARM `.symtab`, `.strtab`, static glibc sections `__libc_freeres_fn`, `__libc_subfreeres`, `__libc_IO_vtables`, `__libc_atexit`; no `.debug_*` sections or embedded home-directory source paths. Embedded numerical version strings include CBC 2.10.10 and 1.2.11; the latter is consistent with zlib, but is not itself a complete version attribution. Embedded compiler identity is GCC (Debian 10.2.1-6) 10.2.1 20210110. These do not establish exact dependency source or compiler invocation.
- Win32 strings explicitly say gzip/bzip2 support was not compiled into COIN. Avoid inventing linked zlib/bzip2 dependencies for this binary solely because other platforms include them.

## Reviewer decision boundary

Source is available for the named CBC versions and known component versions; all preserved source/license/build records should be offered as an honest packet. Absence of reproducible build attestations is not automatically a license violation or an invented requirement. Conversely, version tags, nearby history, recipe defaults, or identical top-level version strings cannot prove the exact source of custom static binary dependencies.

Root and the assigned reviewer must decide whether the available primary distributor/source records plus preserved notices satisfy the actual W04 acceptance requirement. If exact historical input-to-binary association is required, the remaining unavailable fact is a builder/distributor manifest for ARM and Win32, plus the historical AMPL submodule/container/runtime choices already listed in the existing memo. Only those upstream builders/distributors can authenticate those missing historical choices; no local version guess closes them. No upstream messaging is authorized by this task, so none was sent. This note does not self-admit the library or enable a flag.

## Delivery boundary retained

The existing authenticated source-offer implementation supports a single PM4Py archive bounded to 64 MiB. The intact AMPL source (52,745,543 bytes), PuLP source (16,301,847 bytes), MP source (1,396,530 bytes), and CBC monolithic source (13,677,619 bytes) already exceed that bound together; other version/source archives add further bytes. No archive is pruned, silently omitted, or advertised as a complete packet.

A later reviewed delivery design may bind a fixed multipart manifest to the admitted product revision, retain each original archive as an artifact of at most 64 MiB, and serve authenticated chunks of at most 1 MiB with exact artifact hashes, lengths and final reconstruction checks. This record changes no delivery route, budget, flag, or admission. The coordinator owns the actual product binding and assigned reviewer decision.
