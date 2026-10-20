
## Public metadata closure — October 19, 2026

Rows below close public supplier metadata gaps from
[W04-public-supplier-completeness-2026-10-14.md](W04-public-supplier-completeness-2026-10-14.md).
This is metadata association only. Every qualification, delivery, product, and
runtime flag remains false. No wheel bytes were fetched; wheel SHA values are
PyPI metadata declarations, not independently computed payload hashes.

### Candidate wheel and sdist identities (PyPI metadata declarations)

| Package | Candidate wheel | Wheel SHA256 (declared) | Sdist SHA256 (fetched+verified) | Sdist size |
|---|---|---|---|---|
| CVXOPT 1.3.3 | `cvxopt-1.3.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | `5989859412e3f231cb682357a50919c4ce8303764f8612c9377c65a3360ce5ec` | `8059cef41f1f115c87bc9b75fec9f86db95e7f0afcf03a52d619ba433e443bcb` | 8,869,103 |
| SciPy 1.18.1 | `scipy-1.18.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` | `f55fa87b6c612ecd6b058f167c53231b1d14e412efe361d3d6e38b3631c73218` | `52c4b7422442aba924d03ad4019852b08a92e64ea187b933135687bfe2747307` | 30,781,235 |
| PuLP 3.3.0 | `PuLP-3.3.0-py3-none-any.whl` | `dd6ad2d63f196d1254eddf9dcff5cd224912c1f046120cb7c143c5b0eda63fae` | `7eb99b9ce7beeb8bbb7ea9d1c919f02f003ab7867e0d1e322f2f2c26dd31c8ba` | 16,301,847 |

All three packages keep `actual_wheel: null` in the association contract until
an independently approved actual package selection is evidenced.

### CVXOPT 1.3.3 Linux component names (documented build settings, not build receipts)

| Component | Documented enablement | Exact wheel-linked version | Source archive | Notice | Build association |
|---|---|---|---|---|---|
| OpenBLAS | Linked against | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| DSDP | Optional extension included | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| GLPK | Optional extension included | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| GSL | Optional extension included | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| FFTW | Optional extension included | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

The sdist `pyproject.toml` configures these five; the official installation page
confirms Linux wheels link OpenBLAS and include all four extensions. Neither
establishes the candidate wheel's exact component versions or build inputs.

### SciPy 1.18.1 bundled component index (27 names, exact order preserved)

Component names retained from the pinned public `LICENSES_bundled.txt`
(SHA256 `45b1a2cf4eb57277812fcbca2b6af7d84e98c942a5e4dcc360610f49de16c63f`):
fast_matrix_market, pystreambuf, fast_float, ryu, L-BFGS-B, LAPJVsp, SuperLU,
ARPACK, Qhull, xsf, pyduccfft, ducc0, uarray, ampgo, pybind11, HiGHS, Boost,
Biasedurn, UNU.RAN, NumPy, array-api-compat, array-api-extra, Tempita, Chebfun,
getLebedevSphere, prima, packaging.version.

Source/notice/build associations remain UNKNOWN for every component. Two public
path descriptions do not match the fetched source archive: L-BFGS-B (index says
`scipy/optimize/lbfgsb/[__lbfgsb.h,__lbfgsb.c]`, archive has
`scipy/optimize/src/lbfgsb.c` + `lbfgsb.h`); ARPACK (index says
`scipy/sparse/linalg/_eigen/arpack/ARPACK/*`, archive `meson.build` compiles
`arnaud/src/...`). These are source-path mapping mismatches requiring supplier
clarification, not classified defects. pybind11 binary artifacts ship with every
binary build while no pybind11 source files are included.

### CBC binary associations (established public facts retained)

| Payload | Established association | Missing build/source/license |
|---|---|---|
| Linux i32 | Byte-identical AMPL v20191215 CBC 2.10.3 asset | Historical `mp` checkout, image digest, compiler/runtime; linked notice/source |
| Linux i64 | Byte-identical AMPL v20191215 CBC 2.10.3 asset | Same AMPL historical inputs |
| macOS i64 | Byte-identical AMPL v20191215 CBC 2.10.3 asset | Historical `mp` checkout and build/runtime inputs |
| Windows i64 | PuLP PR426 bytes differ from AMPL only in PE timestamps | Signed historical build association |
| Windows i32 | PuLP PR426 identifies CBC 2.9.7 | Exact binary-to-build/source/dependency association |
| Linux ARM64 | PuLP PR685 identifies CBC 2.10.10 | Docker digest, coinbrew/CBC/dependency commits; EPL label discrepancy |

Seven original PuLP notice hashes are retained unchanged. All delivery and
qualification flags remain false. This closure does not qualify PM4Py or any
package and does not change product/runtime state.
