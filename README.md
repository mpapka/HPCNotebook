# HPCNotebook

Hands-on lab series for **CS 455 — Introduction to High Performance Computing** at UIC.
Each lab is a Jupyter notebook that teaches a slice of the HPC stack — logging in, batch
scheduling, serial baselines, OpenMP, MPI, hybrid parallelism, GPUs, scaling studies,
libraries, and parallel I/O — by having students *build and run real code on a real
supercomputer* (**ALCF Crux** primary, **ALCF Polaris** for the GPU labs, Slurm callouts
throughout for other sites).

## How students use it

The labs are launched from the class JupyterHub, **not** cloned by hand. Each **Launch**
button on the course site is an [nbgitpuller](https://nbgitpuller.readthedocs.io/) link
that pulls the **`release`** branch (see *Releasing labs* below) into the student's
`~/HPCNotebook` and opens the lab. A student's next Launch click fast-forwards their
copy to the latest `release` — so fixes reach everyone automatically, and students only
ever have the notebooks that have been released.

The Hub is **not on the cluster**. Every compute cell drives the cluster over `ssh` /
`scp` (via `sshRun`, `sshPut`, `sshGet`, `submitJob`, `waitJob` in `labHelpers.py`),
using the student's own passwordless key set up in **lab00**. The notebook is the driver;
the work runs on Crux (or Polaris, for the GPU labs).

Students sign in to the Hub with an instructor-issued account and password (they don't
clone, push, or manage credentials themselves).

## Language

Everything that runs on a compute node is **C / C++** (the course's stated prerequisite is
CS 251, working knowledge of C/C++). Python is used only in the notebook driver cells and
for post-run data analysis and figure generation.

## Releasing labs (weekly rollout, instructor)

Two branches:

- **`main`** — where you develop and test (all notebooks + these docs + `publish.sh`).
  Test agents clone `main`. Students never see it.
- **`release`** — what students pull. It holds only `labHelpers.py` plus the notebooks
  that have been released so far. Orphan history, so the docs never appear even in
  `git log`.

Release one or more labs with a single command:

```bash
./publish.sh lab01                     # accepts lab01, lab01SerialBaseline, or a full filename
./publish.sh lab01 lab02               # several at once
./publish.sh --list                    # show what students currently have
```

`publish.sh` does both halves of a rollout: it copies the notebook(s) + current
`labHelpers.py` onto `release` **and** flips `published: true` on the matching
course-site lab card so the Labs page starts listing that lab (the site auto-deploys
on push). Until a lab is published, students cannot pull it and its card is not built.
Develop freely on `main`; ship week by week.

Notes:
- A dedicated worktree, `../HPCNotebook-release`, is created automatically so your `main`
  checkout is never disturbed.
- The course-site checkout is assumed at `../UIC_Course_Website`; override with
  `COURSE_SITE_DIR`. If the site is absent, only the notebook is released.
- To fix a released lab, just re-run `./publish.sh <lab>` — it re-syncs from `main`.

## Lab order and prerequisites

The numbered notebooks **`lab00` … `lab13`** are the 14-week course sequence and are
meant to be done in order. They share a **spine**: a 2-D heat-equation stencil that
starts life as a serial C program in lab01 and gets progressively parallelized —
OpenMP → MPI → hybrid → GPU → multi-GPU → many-node → parallel I/O — so each lab
produces a number that plugs into a class-wide scaling leaderboard.

| Wk | Lab | Focus |
|---|---|---|
| 1 | `lab00GettingOnTheMachine` | Accounts, ssh (MobilePASS+ multiplexed), `module`, filesystems, first `qsub` on Crux |
| 2 | `lab01SerialBaseline` | 2-D heat stencil in serial C — the "before" number every later lab beats |
| 3 | `lab02PerformanceMeasurement` | Wall vs CPU time, `perf stat`, roofline intuition, why one number lies |
| 4 | `lab03OpenMPFundamentals` | `#pragma omp parallel for`, reductions, first speedup on the baseline |
| 5 | `lab04OpenMPPitfalls` | False sharing, load imbalance, thread affinity, NUMA |
| 6 | `lab05MPIFundamentals` | `MPI_Init`, point-to-point, collectives, first multi-node job |
| 7 | `lab06MPIDomainDecomposition` | Split the stencil across ranks, halo exchange, verify before speed |
| 8 | `lab07HybridMPIOpenMP` | Ranks-per-node × threads-per-rank sweep on Crux |
| 9 | `lab08GPUIntro` | OpenMP `target` offload — port one kernel from lab06 |
| 10 | `lab09GPUOptimization` | CUDA, memory hierarchy, coalescing, occupancy, streams |
| 11 | `lab10MultiGPUOneNode` | 4-GPU Polaris node via MPI+CUDA |
| 12 | `lab11ScalingStudy` | Strong + weak scaling out to many nodes; publication-quality figures |
| 13 | `lab12Libraries` | When to write vs link — BLAS / LAPACK / FFTW / cuBLAS |
| 14 | `lab13IOAndCheckpointing` | Parallel HDF5, why I/O eats scaling, checkpoint / restart |

Week 15 (final week) has no new lab — final exam / project defenses.

### On-ramps (before lab00)

Four optional on-ramps come before the numbered sequence — do any subset, in any order,
or skip them. **AA**, **BB**, and **CC** are independent; **DD** is strongly recommended
because every lab from lab01 on relies on its plotting primitives.

- **AA** `labAALinuxAndSSH` — shell basics, ssh keys, first cluster login
- **BB** `labBBCToolchain` — `gcc` / `clang`, `make`, `gdb`, useful flags, first-hour C hygiene
- **CC** `labCCNumericsForHPC` — floats vs doubles, ULPs, `-ffast-math` traps
  (short — prevents "my parallel version gives different answers!" panic in lab06)
- **DD** `labDDAnalysisAndPlotting` — pandas + matplotlib to turn any lab's `.csv`
  outputs into speedup / efficiency / roofline plots; uses `renderField` and
  `plotScaling` from `labHelpers.py`

### Grad-student capstone (after lab13)

- **EE** `labEENBodyBarnesHut` — the same parallelization arc as the spine, but on
  n-body gravitation with a Barnes-Hut tree. Reuses everything you built from lab01
  through lab11.

## Parallel-track projects

The lab sequence intentionally leaves the three individual projects room to breathe —
labs teach, projects apply.

| Weeks | Project | Feeds from | Notes |
|---|---|---|---|
| 2-3 | Lego decomposition (group) | Precedes lab03 | Pure decomposition thinking before any parallel code |
| 4-6 | OpenMP project (individual) | lab03, lab04 | Due before lab05 |
| 7-10 | MPI project (individual) | lab05, lab06, lab07 | Due before lab08 |

## The runtime these labs target

The primary cluster is **ALCF Crux** (PBS Pro, CPU-only — HPE Cray EX with AMD EPYC).
Labs 00-07 run entirely on Crux. Labs **08-10 switch to Polaris** (also PBS Pro, NVIDIA
A100 GPUs) — that is where GPU work happens. Labs 11-13 return to Crux for scaling
studies, libraries, and parallel I/O.

The switch between clusters is one line in each lab's `setupLab()` call
(`host='crux'` vs `host='polaris'`). Everything else — the ssh multiplexing you set up
in lab00, the scratch pattern under `/eagle/UIC-CS455-Sp2027/<user>/`, the `submitJob`
/ `waitJob` / `sshGet` workflow — is identical on both.

Labs use the SAME notebook cells on any Slurm cluster (UIC ACER Extreme, other
university clusters) because `labHelpers.py` probes the remote scheduler and picks
`qsub` or `sbatch` automatically. Where a syntax difference matters — job scripts,
`PBS_*` vs `SLURM_*` env vars — the notebook shows the PBS version and includes a
**🔀 On a Slurm system** callout with the equivalent.

- **Compute goes through the scheduler** — the login node is for editing and
  submitting, never for running. `labHelpers.sshRun` targets the login node;
  `submitJob` puts the actual work on compute.
- **Filesystem seam** — home is small and slow, `/eagle/UIC-CS455-Sp2027/<user>/` is
  big and fast; every lab writes into `$HPC_SCRATCH/<labName>/` and pulls only the
  small stuff (CSVs, final figures) back to the Hub via `sshGet`. Every job script
  **must** include `#PBS -l filesystems=home:eagle` — the scheduler rejects jobs
  that don't declare filesystems up front.
- **Authentication** — ALCF uses **MobilePASS+**. Lab 00 sets up ssh connection
  multiplexing so students prompt for a passcode once every ~8 hours, not on every
  cell. Every later lab assumes that channel is up.
- **Visualization** — small runs render on the Hub (matplotlib in the notebook, so
  students see the code); big runs render on the compute node and we scp the PNGs
  back. `renderField(mode='auto')` picks based on size and explains which mode it
  chose — that IS the in-situ visualization lesson lab11 leans on.

## Layout

- `lab00` … `lab13` — the labs, in course order.
- `labAALinuxAndSSH`, `labBBCToolchain`, `labCCNumericsForHPC`, `labDDAnalysisAndPlotting`
  — optional on-ramps.
- `labEENBodyBarnesHut` — grad-student capstone.
- `labHelpers.py` — shared toolkit imported by every lab: `setupLab`, `preflight` /
  `checkpoint` graded checks, ssh + scheduler wrappers, `renderField` /
  `plotScaling` / `applyHouseStyle` / `saveFigure`.
