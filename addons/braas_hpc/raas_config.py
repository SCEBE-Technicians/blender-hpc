# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# (c) IT4Innovations, VSB-TUO

"""SCEBE-only RaaS config."""

import bpy

Cluster_items_dict = {
    "SCEBE": "SCEBE GPU Server",
}

Cluster_items = [
    ("SCEBE", "SCEBE GPU Server", ""),
]

Scebe_partitions = [
    ("LocalQ", "LocalQ", ""),
]

JobQueue_items = [
    ("JOB_CPU", "CPU", ""),
    ("JOB_GPU", "GPU", ""),
]

JobQueue_items_dict = {
    "JOB_CPU": "CPU",
    "JOB_GPU": "GPU",
}

from . import raas_jobs
from . import raas_connection

ssh_library_items = [
    ("PARAMIKO", "Paramiko", ""),
    ("SYSTEM", "System", ""),
    ("ASYNCSSH", "AsyncSSH", ""),
]

account_types_items = [
    ("EDUID", "e-INFRA CZ (eduID.cz)", ""),
    ("IT4I", "IT4I", ""),
]


def GetBlenderClusterVersion():
    return (str(bpy.app.version_string)).replace(' ', '_')


async def CreateJob(context, token):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    job_type = blender_job_info_new.job_type

    if blender_job_info_new.cluster_type != 'SCEBE':
        raise ValueError("Unsupported cluster type: %s" % blender_job_info_new.cluster_type)

    if 'JOB_CPU' in job_type:
        await raas_jobs.CreateJobTask3Dep(
            context,
            token,
            raas_jobs.JobTaskInfo(1, 121, 120),
            raas_jobs.JobTaskInfo(1, 121, 121),
            raas_jobs.JobTaskInfo(1, 121, 122),
            2,
            12,
        )
    elif 'JOB_GPU' in job_type:
        await raas_jobs.CreateJobTask3Dep(
            context,
            token,
            raas_jobs.JobTaskInfo(1, 122, 123),
            raas_jobs.JobTaskInfo(1, 122, 124),
            raas_jobs.JobTaskInfo(1, 122, 125),
            2,
            12,
        )


def GetServer(pid):
    return ""  # TODO


def GetServerFromType(cluster_type):
    if cluster_type == 'SCEBE':
        return '146.176.131.129'
    raise ValueError("Unsupported cluster type: %s" % cluster_type)


def GetSchedulerFromContext(context):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    if blender_job_info_new.cluster_type == 'SCEBE':
        return 'SLURM'
    raise ValueError("Unsupported cluster type: %s" % blender_job_info_new.cluster_type)


def GetDAServer(context):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    return GetServerFromType(blender_job_info_new.cluster_type)


def GetDAClusterPath(context, project_dir, pid):
    return project_dir + '/braas-hpc/direct'


def GetDAOpenCallProject(pid):
    return pid


def GetDAQueueMPIProcs(CommandTemplateId):
    if CommandTemplateId == 124:
        return 1  # GPUs
    return 0


# return cores,queue,script
def GetDAQueueScript(ClusterId, CommandTemplateId):
    if ClusterId != 12:
        return None, None

    if CommandTemplateId == 120:
        return 1, '~/braas-hpc/scripts/scebe-gpu-server-slurm/job_init.sh'
    elif CommandTemplateId == 121:
        return 1, '~/braas-hpc/scripts/scebe-gpu-server-slurm/run_blender_cpu.sh'
    elif CommandTemplateId == 122:
        return 1, '~/braas-hpc/scripts/scebe-gpu-server-slurm/job_finish.sh'
    elif CommandTemplateId == 123:
        return 1, '~/braas-hpc/scripts/scebe-gpu-server-slurm/job_init.sh'
    elif CommandTemplateId == 124:
        return 1, '~/braas-hpc/scripts/scebe-gpu-server-slurm/run_blender_gpu.sh'
    elif CommandTemplateId == 125:
        return 1, '~/braas-hpc/scripts/scebe-gpu-server-slurm/job_finish.sh'

    return None, None


def GetDAJobSpecialFlags(context, ClusterId, CommandTemplateId, pid_queue):
    custom_flags = ''
    if ClusterId == 12 and 'JOB_GPU' in context.scene.raas_blender_job_info_new.job_type:
        custom_flags += ' --gres=gpu:1'
    return custom_flags


def GetGitAddonCommand(repository, branch):
    return 'if [ -d ~/braas-hpc ] ; then rm -rf ~/braas-hpc ; fi ; git clone -q -b ' + branch + ' ' + repository


def GetBlenderInstallCommand(preset, url_link):
    filename = url_link.split('/')[-1]
    extracted_string = filename.replace('.tar.xz', '')

    return 'if [ -d ~/blender ] ; then rm -rf ~/blender ; fi ; \
        cd ~/ ; wget -O blender.tar.xz -q %s ; \
        tar -xf blender.tar.xz ; mv %s ~/blender ; rm blender.tar.xz ; \
            ' % (url_link, extracted_string)


def GetBlenderPatchCommand(preset, url_link):
    return ''


def GetCurrentPidInfo(context, preferences):
    blender_job_info_new = context.scene.raas_blender_job_info_new
    name = blender_job_info_new.job_allocation
    queue = blender_job_info_new.job_partition
    dir = blender_job_info_new.job_remote_dir

    return name, queue, dir


def SetPidDir(preset):
    if preset.cluster_name != "SCEBE":
        raise Exception("Unknown cluster name")

    cmd = 'echo $HOME'
    server = GetServerFromType(preset.cluster_name.upper())
    res = raas_connection.ssh_command_sync(server, cmd, preset)
    preset.working_dir = res.strip()


class RaasConfigFunctions:
    """Class that holds pointers to all functions."""

    def __init__(self):
        self.create_job = CreateJob
        self.get_server_from_type = GetServerFromType
        self.get_scheduler_from_context = GetSchedulerFromContext
        self.get_da_server = GetDAServer
        self.get_da_cluster_path = GetDAClusterPath
        self.get_da_open_call_project = GetDAOpenCallProject
        self.get_da_queue_mpi_procs = GetDAQueueMPIProcs
        self.get_da_queue_script = GetDAQueueScript
        self.get_special_job_flags = GetDAJobSpecialFlags
        self.get_git_addon_command = GetGitAddonCommand
        self.get_blender_install_command = GetBlenderInstallCommand
        self.get_blender_patch_command = GetBlenderPatchCommand
        self.get_current_pid_info = GetCurrentPidInfo
        self.set_pid_dir = SetPidDir

    async def call_create_job(self, context, token):
        return await self.create_job(context, token)

    def call_get_server_from_type(self, cluster_type):
        return self.get_server_from_type(cluster_type)

    def call_get_scheduler_from_context(self, context):
        return self.get_scheduler_from_context(context)

    def call_get_da_server(self, context):
        return self.get_da_server(context)

    def call_get_da_cluster_path(self, context, project_dir, pid):
        return self.get_da_cluster_path(context, project_dir, pid)

    def call_get_da_open_call_project(self, pid):
        return self.get_da_open_call_project(pid)

    def call_get_da_queue_mpi_procs(self, command_template_id):
        return self.get_da_queue_mpi_procs(command_template_id)

    def call_get_da_queue_script(self, cluster_id, command_template_id):
        return self.get_da_queue_script(cluster_id, command_template_id)

    def call_get_special_job_flags(self, context, cluster_id, command_template_id, pid_queue):
        return self.get_special_job_flags(context, cluster_id, command_template_id, pid_queue)

    def call_get_git_addon_command(self, repository, branch):
        return self.get_git_addon_command(repository, branch)

    def call_get_blender_install_command(self, preset, url_link):
        return self.get_blender_install_command(preset, url_link)

    def call_get_blender_patch_command(self, preset, url_link):
        return self.get_blender_patch_command(preset, url_link)

    def call_get_current_pid_info(self, context, preferences):
        return self.get_current_pid_info(context, preferences)

    def call_set_pid_dir(self, preset):
        return self.set_pid_dir(preset)
