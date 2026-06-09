import logging

import bpy
from bpy.types import Operator
from bpy.props import EnumProperty, StringProperty

from . import raas_pref
from . import raas_config
from . import raas_connection


log = logging.getLogger(__name__)

Page_items = [
    ('DEPENDENCIES', 'Dependencies', ''),
    ('CONNECTION', 'Connection', ''),
    ('INSTALL', 'Install', ''),
]

Auth_items = [
    ('KEY', 'SSH Key', ''),
    ('PASSWORD', 'Password', ''),
]


class SetupConnectionPreset:
    def __init__(self, cluster, username, auth_method, password, key_path, key_password):
        self.cluster_name = cluster
        self.raas_da_username = username
        self.raas_da_password = password
        self.raas_da_use_password = auth_method == 'PASSWORD'
        self.raas_private_key_path = key_path
        self.raas_private_key_password = key_password
        self.raas_ssh_library = 'PARAMIKO'


def default_partition(cluster):
    partitions = getattr(raas_config, "%s_partitions" % cluster.capitalize(), [])
    if not partitions:
        return ''
    return partitions[0][0]


def upsert_cluster_preset(context, cluster, username, auth_method, password, key_path, key_password):
    log.info("Setup wizard updating preferences for %s as %s", cluster, username)

    prefs = raas_pref.preferences()
    preset = None
    partition_names = [partition[0] for partition in getattr(raas_config, "%s_partitions" % cluster.capitalize(), [])]

    for existing_preset in prefs.cluster_presets:
        if existing_preset.cluster_name == cluster:
            preset = existing_preset
            break

    if preset is None:
        preset = prefs.cluster_presets.add()
        log.info("Setup wizard created new %s preset", cluster)
    else:
        log.info("Setup wizard updating existing %s preset", cluster)

    preset.cluster_name = cluster
    if preset.partition_name not in partition_names:
        preset.partition_name = default_partition(cluster)
    preset.raas_da_username = username
    preset.raas_da_password = password
    preset.raas_da_use_password = auth_method == 'PASSWORD'
    preset.raas_private_key_path = key_path
    preset.raas_private_key_password = key_password
    preset.raas_ssh_library = 'PARAMIKO'
    preset.is_enabled = True

    if not preset.working_dir:
        log.info("Setup wizard finding working directory for %s", cluster)
        context.scene.raas_config_functions.call_set_pid_dir(preset)
        log.info("Setup wizard working directory for %s: %s", cluster, preset.working_dir)

    return preset


def open_setup_wizard_next_tick(**kwargs):
    def open_wizard():
        log.info("Setup wizard opening page: %s", kwargs.get('page', 'DEPENDENCIES'))
        bpy.ops.raas.setup_wizard('INVOKE_DEFAULT', **kwargs)
        return None

    bpy.app.timers.register(open_wizard, first_interval=0.1)


class RAAS_OT_setup_install_cluster(Operator):
    bl_idname = 'raas.setup_install_cluster'
    bl_label = 'Install Blender and Scripts'
    bl_description = 'Install blender-hpc scripts and Blender on the configured cluster'

    cluster: EnumProperty(
        name='Cluster',
        items=raas_config.Cluster_items,
        default='ENUCC'
    )  # type: ignore

    username: StringProperty(
        name='Username',
        default=''
    )  # type: ignore

    auth_method: EnumProperty(
        name='Authentication',
        items=Auth_items,
        default='KEY'
    )  # type: ignore

    password: StringProperty(
        name='Password',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    private_key_path: StringProperty(
        name='Private Key Path',
        subtype='FILE_PATH',
        default=''
    )  # type: ignore

    private_key_password: StringProperty(
        name='Key Passphrase',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    def execute(self, context):
        log.info("Setup wizard install started for %s", self.cluster)

        preset = upsert_cluster_preset(
            context,
            self.cluster,
            self.username.strip(),
            self.auth_method,
            self.password,
            self.private_key_path,
            self.private_key_password
        )

        if not raas_pref.preferences().check_valid_settings(preset, type='INSTALL_SCRIPTS'):
            return {'CANCELLED'}

        scripts_repository = raas_pref.preferences().raas_scripts_repository
        scripts_branch = raas_pref.preferences().raas_scripts_repository_branch
        blender_link = raas_pref.preferences().raas_blender_link
        server = context.scene.raas_config_functions.call_get_server_from_type(self.cluster)

        try:
            cmd = context.scene.raas_config_functions.call_get_git_addon_command(scripts_repository, scripts_branch)
            if cmd:
                log.info("Setup wizard installing scripts on %s with command: %s", self.cluster, cmd)
                raas_connection.ssh_command_sync(server, cmd, preset)

                script_dir = 'scebe-gpu-server-slurm' if self.cluster == 'SCEBE' else 'enucc-slurm'
                check_cmd = 'test -d ~/blender-hpc/scripts/%s && echo OK' % script_dir
                log.info("Setup wizard verifying scripts on %s with command: %s", self.cluster, check_cmd)
                res = raas_connection.ssh_command_sync(server, check_cmd, preset)
                if res.strip() != 'OK':
                    raise Exception("Scripts were not found after install: ~/blender-hpc/scripts/%s" % script_dir)

            cmd = context.scene.raas_config_functions.call_get_blender_install_command(preset, blender_link)
            if cmd:
                log.info("Setup wizard installing Blender on %s with command: %s", self.cluster, cmd)
                raas_connection.ssh_command_sync(server, cmd, preset)

            cmd = context.scene.raas_config_functions.call_get_blender_patch_command(preset, blender_link)
            if cmd:
                log.info("Setup wizard applying Blender patches on %s with command: %s", self.cluster, cmd)
                raas_connection.ssh_command_sync(server, cmd, preset)

        except Exception as err:
            log.exception("Setup wizard install failed for %s", self.cluster)
            self.report({'ERROR'}, 'Install failed: %s' % err)
            return {'CANCELLED'}

        raas_pref.preferences().raas_scripts_installed = True
        log.info("Setup wizard install finished for %s", self.cluster)
        self.report({'INFO'}, 'Installed Blender and scripts on %s.' % self.cluster)
        return {'FINISHED'}


class RAAS_OT_setup_wizard(Operator):
    bl_idname = 'raas.setup_wizard'
    bl_label = 'Setup Wizard'
    bl_description = 'Open the blender-hpc setup wizard'

    page: EnumProperty(
        name='Page',
        items=Page_items,
        default='DEPENDENCIES',
        options={'HIDDEN'}
    )  # type: ignore

    cluster: EnumProperty(
        name='Cluster',
        items=raas_config.Cluster_items,
        default='ENUCC'
    )  # type: ignore

    username: StringProperty(
        name='Username',
        default=''
    )  # type: ignore

    auth_method: EnumProperty(
        name='Authentication',
        items=Auth_items,
        default='KEY'
    )  # type: ignore

    password: StringProperty(
        name='Password',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    private_key_path: StringProperty(
        name='Private Key Path',
        subtype='FILE_PATH',
        default=''
    )  # type: ignore

    private_key_password: StringProperty(
        name='Key Passphrase',
        default='',
        subtype='PASSWORD'
    )  # type: ignore

    def invoke(self, context, event):
        if not self.private_key_path:
            self.private_key_path = raas_connection.autodetect_private_key_file()
            if self.private_key_path:
                log.info("Setup wizard auto-detected private key: %s", self.private_key_path)

        if self.page == 'DEPENDENCIES':
            confirm_text = 'Next'
        elif self.page == 'CONNECTION':
            confirm_text = 'Connect'
        else:
            confirm_text = 'Finish'

        try:
            return context.window_manager.invoke_props_dialog(self, width=420, confirm_text=confirm_text)
        except TypeError:
            return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.label(text='Welcome to setup')

        if self.page == 'DEPENDENCIES':
            self.draw_dependencies_page(layout)
            return

        if self.page == 'CONNECTION':
            self.draw_connection_page(layout)
            return

        self.draw_install_page(layout)

    def draw_dependencies_page(self, layout):
        if raas_pref.preferences().dependencies_installed:
            log.debug("Setup wizard dependencies page: dependencies installed")
            layout.label(text='Dependencies are installed.', icon='CHECKMARK')
        else:
            log.debug("Setup wizard dependencies page: dependencies missing")
            layout.label(text='Dependencies are not installed.', icon='ERROR')
            layout.operator(raas_pref.RAAS_OT_install_dependencies.bl_idname, icon='CONSOLE')

    def draw_connection_page(self, layout):
        layout.prop(self, 'cluster')
        layout.prop(self, 'username')
        layout.prop(self, 'auth_method', expand=True)

        if self.auth_method == 'PASSWORD':
            layout.prop(self, 'password')
        else:
            layout.prop(self, 'private_key_path')
            layout.prop(self, 'private_key_password')

    def draw_install_page(self, layout):
        layout.label(text='Connection verified.')
        layout.label(text='Install Blender and scripts on the selected cluster.')
        props = layout.operator(RAAS_OT_setup_install_cluster.bl_idname, icon='CONSOLE')
        props.cluster = self.cluster
        props.username = self.username
        props.auth_method = self.auth_method
        props.password = self.password
        props.private_key_path = self.private_key_path
        props.private_key_password = self.private_key_password

    def execute(self, context):
        log.info("Setup wizard executing page: %s", self.page)

        if self.page == 'DEPENDENCIES':
            if not raas_pref.preferences().dependencies_installed:
                log.info("Setup wizard blocked: dependencies are not installed")
                self.report({'ERROR'}, 'Install dependencies before continuing.')
                return {'CANCELLED'}

            open_setup_wizard_next_tick(
                page='CONNECTION',
                cluster=self.cluster,
                username=self.username,
                auth_method=self.auth_method,
                password=self.password,
                private_key_path=self.private_key_path,
                private_key_password=self.private_key_password
            )
            return {'FINISHED'}

        if self.page == 'INSTALL':
            return {'FINISHED'}

        username = self.username.strip()
        if not username:
            log.info("Setup wizard connection blocked: username missing")
            self.report({'ERROR'}, 'Username is required.')
            return {'CANCELLED'}

        if self.auth_method == 'PASSWORD':
            if not self.password:
                log.info("Setup wizard connection blocked: password missing")
                self.report({'ERROR'}, 'Password is required.')
                return {'CANCELLED'}
        else:
            if not self.private_key_path:
                self.private_key_path = raas_connection.autodetect_private_key_file()
            if not self.private_key_path:
                log.info("Setup wizard connection blocked: private key missing")
                self.report({'ERROR'}, 'Private key file is required.')
                return {'CANCELLED'}

        preset = SetupConnectionPreset(
            self.cluster,
            username,
            self.auth_method,
            self.password,
            self.private_key_path,
            self.private_key_password
        )

        try:
            server = raas_config.GetServerFromType(self.cluster)
            log.info("Setup wizard testing connection to %s (%s) as %s", self.cluster, server, username)
            result = raas_connection.ssh_command_sync(server, 'hostname', preset)
            log.info("Setup wizard connection to %s succeeded: %s", self.cluster, result.strip())
            upsert_cluster_preset(
                context,
                self.cluster,
                username,
                self.auth_method,
                self.password,
                self.private_key_path,
                self.private_key_password
            )
        except Exception as err:
            log.exception("Setup wizard connection to %s failed", self.cluster)
            self.report({'ERROR'}, 'Connection failed: %s' % err)
            return {'CANCELLED'}

        self.report({'INFO'}, 'Connected to %s: %s' % (self.cluster, result.strip()))
        open_setup_wizard_next_tick(
            page='INSTALL',
            cluster=self.cluster,
            username=username,
            auth_method=self.auth_method,
            password=self.password,
            private_key_path=self.private_key_path,
            private_key_password=self.private_key_password
        )
        return {'FINISHED'}


def register():
    bpy.utils.register_class(RAAS_OT_setup_install_cluster)
    bpy.utils.register_class(RAAS_OT_setup_wizard)


def unregister():
    bpy.utils.unregister_class(RAAS_OT_setup_wizard)
    bpy.utils.unregister_class(RAAS_OT_setup_install_cluster)
