# blender-hpc ENU Rendering Add-on

A Blender add-on for submitting Cycles render jobs to Edinburgh Napier University HPC resources, including ENUCC and the SCEBE GPU server.

This project is a fork of the original [blender-hpc](https://github.com/It4innovations/blender-hpc) project from IT4Innovations. The fork adapts the add-on for direct SSH-based rendering workflows on Edinburgh Napier University infrastructure, with bundled Slurm scripts for ENUCC and `scebe-gpu-server`.

## What It Does

The add-on packages a Blender scene, copies it to a remote HPC system over SSH, submits a Slurm render job, tracks job state, and downloads rendered outputs and logs back to the local workstation.

It is intended for artists, researchers, and technical users who want to render Blender scenes on remote CPU/GPU resources without manually writing Slurm scripts for each job.

## Supported Targets

| Target | Scheduler | Status |
| --- | --- | --- |
| SCEBE GPU Server | Slurm | Supported by bundled scripts |
| ENUCC | Slurm | Supported by bundled scripts |

Current bundled scripts are in:

```text
scripts/scebe-gpu-server-slurm/
scripts/enucc-slurm/
```

The current SCEBE server configuration uses:

```text
Host: scebe-gpu-server
Address: 146.176.131.129
Partition: LocalQ
Scheduler: Slurm
```

The current ENUCC configuration uses:

```text
Host: login.enucc.napier.ac.uk
Partitions: short, long, himem, gpu
Scheduler: Slurm
```

The ENUCC `nodes` partition is intentionally not exposed by the add-on.

## Key Features

- Submit Blender render jobs from inside Blender.
- Render single images or animations.
- Support CPU and GPU render modes.
- Use Slurm job submission on the remote server.
- Package `.blend` files with external resources before upload.
- Transfer job files over SSH/SCP-style connections.
- Monitor submitted jobs from the Blender UI.
- Cancel queued or running jobs.
- Download rendered outputs, logs, and job metadata.
- Write add-on logs to a persistent Blender config log file.
- Supports Paramiko, AsyncSSH, and system SSH modes.

## Requirements

### Local Machine

- Blender 4.0 or newer.
- Python bundled with Blender.
- Network access to the target HPC server.
- SSH credentials for the target system.
- A local directory for job storage.

### Python Dependencies

The add-on can install these from Blender preferences:

- `paramiko`
- `scp`
- `asyncssh`

### Remote HPC System

The remote system needs:

- SSH access for your user account.
- Slurm commands available, such as `sbatch`, `squeue`, and `scancel`.
- Blender installed at `~/blender/blender`, or installed through the add-on setup workflow.
- The render helper scripts installed under `~/blender-hpc/scripts/...`.
- A writable working directory, usually under your home directory or project storage.

For SCEBE, Slurm accounting may be disabled, so the add-on uses `squeue` and local `.job` files rather than relying on `sacct`.

## Installation

### 1. Package The Add-on

From the repository root, create a zip containing the Blender add-on folder:

```powershell
Compress-Archive -Path addons\blender_hpc -DestinationPath blender_hpc.zip -Force
```

The zip should contain this structure:

```text
blender_hpc/
  __init__.py
  raas_config.py
  raas_render.py
  ...
```

Do not zip the whole repository unless the top-level folder inside the zip is `blender_hpc`.

### 2. Install In Blender

1. Open Blender.
2. Go to `Edit > Preferences > Add-ons`.
3. Click `Install...`.
4. Select `blender_hpc.zip`.
5. Enable `System: blender-hpc`.

### 3. Install Dependencies

In the add-on preferences:

1. Expand `blender-hpc`.
2. Click `Install Dependencies`.
3. Restart Blender if prompted.

### 4. Configure A Cluster Preset

In `Edit > Preferences > Add-ons > blender-hpc`:

1. Add a cluster preset.
2. Select the cluster, for example `SCEBE GPU Server` or `ENUCC`.
3. Set the partition, for example `LocalQ` on SCEBE or `gpu`/`short`/`long`/`himem` on ENUCC.
4. Select job type, usually `GPU` for GPU rendering.
5. Enter your remote username.
6. Configure SSH authentication.
7. Set or discover the working directory.
8. Enable the preset.

### 5. Install Scripts And Blender On The Server

In the add-on preferences:

1. Set the scripts repository URL and branch.
2. Set the Blender Linux tarball URL if Blender is not already installed remotely.
3. Click `Install scripts and Blender on the cluster(s)`.
4. Alternatively, install manually and enable `Scripts already installed`.

Expected remote script paths:

```text
~/blender-hpc/scripts/scebe-gpu-server-slurm/
~/blender-hpc/scripts/enucc-slurm/
~/blender/blender
```

## Usage

### 1. Open The Add-on Panel

1. Open your Blender scene.
2. Set render engine to `Cycles`.
3. Open the `Render Properties` tab.
4. Expand `blender-hpc`.

### 2. Configure The Job

In `New Job`:

- Select the cluster preset.
- Enter a project/job name.
- Choose `Image` or `Animation`.
- Choose `CPU` or `GPU` depending on the preset.
- Set walltime in minutes.
- For animations, set frame range and max jobs.

For a single image, the current frame is rendered.

For an animation, frames are submitted through a Slurm array. Each array task renders part of the frame range. GPU jobs request one GPU with `--gres=gpu:1`.

### 3. Submit The Job

Click `Submit Job`.

The add-on will:

1. Save a temporary packed `.blend` file.
2. Copy the job directory to the remote server.
3. Submit init, render, and finish jobs through Slurm.
4. Create/update a `.job` status file.
5. Refresh the job list.

### 4. Monitor Jobs

Use the `Jobs` panel:

- Click `Refresh` to reload job states.
- Select a job to see details.
- Use `Cancel` to stop a queued or running job.

Known states include:

- `CONFIGURING`
- `QUEUED`
- `RUNNING`
- `FINISHED`
- `FAILED`
- `CANCELED`

### 5. Download Results

Select a job and click `Download results`.

The add-on downloads:

```text
out/   rendered frames or images
log/   Blender stdout/stderr logs
job/   job metadata
```

Files are stored under the local job storage directory configured in add-on preferences.

## Render Scripts

Each Slurm script set contains:

```text
job_init.sh
run_blender_cpu.sh
run_blender_gpu.sh
job_finish.sh
use_gpu.py
```

`run_blender_gpu.sh` runs Blender in background mode with Cycles and executes `use_gpu.py` to select GPU rendering.

The ENUCC script set is located at:

```text
scripts/enucc-slurm/
```

ENUCC submissions include `--time=<hh:mm:ss>` in the generated `sbatch` command.

Animation jobs render frames as individual frame outputs. The add-on does not stitch frames into a video. If you need a video file, render frames first and assemble them afterward using Blender, FFmpeg, or another tool.

## Logging

The add-on writes logs to Blender's user config directory:

```text
C:\Users\<user>\AppData\Roaming\Blender Foundation\Blender\<version>\config\blender-hpc\blender-hpc.log
```

For example:

```text
C:\Users\40021033\AppData\Roaming\Blender Foundation\Blender\5.1\config\blender-hpc\blender-hpc.log
```

Use this log when debugging submit, transfer, SSH, or job-list issues. Python tracebacks are written there for operator failures.

## Troubleshooting

### Add-on Does Not Appear In Blender

Check the zip structure. Blender must see `blender_hpc/__init__.py` at the top level inside the zip.

### Test Connection Is Skipped

The selected preset is disabled. In add-on preferences, check:

- Username is set.
- SSH key/password settings are valid.
- Working directory is set.
- Preset is enabled.

### Slurm Accounting Is Disabled

If `sacct` fails, this is expected on direct Slurm targets where accounting is unavailable. The add-on uses `squeue` and `.job` files instead.

### No Jobs Appear In The Job List

Check the remote job files:

```bash
ls -la ~/blender-hpc/direct/<username>/scebe/*.job
cat ~/blender-hpc/direct/<username>/scebe/*.job
```

For ENUCC, replace `scebe` with `enucc`.

The add-on parses these `.job` files to populate the Blender job list.

### GPU Render Does Not Use The GPU

Check the remote log files in the job `log/` directory. Also confirm:

- The job type is `GPU`.
- The Slurm submission includes `--gres=gpu:1`.
- Blender can see the GPU on the remote server.
- `use_gpu.py` is installed in the expected scripts directory.

## Project Layout

```text
addons/blender_hpc/                  Blender add-on source
scripts/scebe-gpu-server-slurm/    SCEBE Slurm render scripts
scripts/enucc-slurm/               ENUCC Slurm render scripts
img/                               README/UI images from the original project
doc/                               Additional documentation
```

## Fork Notice

This repository is a fork of blender-hpc. The original project was developed by IT4Innovations National Supercomputing Center.

Original project:

```text
https://github.com/It4innovations/blender-hpc
```

This fork is adapted for Edinburgh Napier University HPC rendering workflows.

## License

This project follows the license of the original blender-hpc project. See [LICENSE](LICENSE).
