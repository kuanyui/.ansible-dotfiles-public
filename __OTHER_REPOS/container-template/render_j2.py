from dataclasses import dataclass, field
from typing import List, Optional, Final, Literal, cast
from jinja2 import Environment, FileSystemLoader
import os
import shutil

BASE_DIR: Final[str] = os.path.dirname(os.path.abspath(__file__))
J2_ROOT = os.path.join(BASE_DIR, 'j2')
OUTPUT_DIR = os.path.join(BASE_DIR, 'rendered')

DockerPlatform = Literal["linux/amd64"]
DockerImage = Literal["debian:12", "debian:13"]
FeaturePresets = Literal["zsh", "emacs", "qemacs"]

@dataclass
class NodejsConfig:
    npm_global_pkgs: List[str] = field(default_factory=lambda: cast(List[str], []))

@dataclass
class AgentConfig:
    '''A `c-<target_suffix>` Makefile target will be generated that runs `command` in the container.'''
    target_suffix: str
    command: str
    display_name: str = ""
    '''Used in the Makefile target's help text ("## [Container] Run <display_name>"). Defaults to `target_suffix`.'''

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.target_suffix

@dataclass
class ContainerConfig:
    name: str
    naming_prefix: str
    '''Prefix for IMAGE_NAME / CONTAINER_NAME in Makefile (e.g., "claude_code" gives `claude_code_image__$(PROJECT_NAME)`).'''
    image_platform: DockerPlatform
    image_name: DockerImage
    tz: Optional[str] = None
    distro_pkgs: List[str] = field(default_factory=lambda: cast(List[str], []))
    '''Note that package names may differ among different distros.'''
    feature_presets: List[FeaturePresets] = field(default_factory=lambda: cast(List[FeaturePresets], []))
    '''The actual package names may differ among different distros.'''
    nodejs: Optional[NodejsConfig] = None
    agent: Optional[AgentConfig] = None
    publish_ports: List[str] = field(default_factory=lambda: cast(List[str], []))
    '''Each entry is a `--publish` arg, e.g. "1455:1455/tcp".'''

    @property
    def distro(self) -> Optional[str]:
        name = self.image_name.lower()
        if 'debian' in name or 'ubuntu' in name:
            return 'debian'
        if 'alpine' in name:
            return 'alpine'
        if 'suse' in name:    # 'opensuse/leap', 'opensuse/tumbleweed'
            return 'suse'
        if any(x in name for x in ['fedora', 'rocky', 'centos']):
            return 'redhat'
        return None

    @property
    def obs_repo_name(self) -> str:
        image_name = self.image_name
        low_name = image_name.lower()
        if 'debian:' in low_name:
            return image_name.replace('debian:', 'Debian_')
        if 'ubuntu:' in low_name:
            return image_name.replace('ubuntu:', 'xUbuntu_')
        if 'tumbleweed' in low_name:
            return 'openSUSE_Tumbleweed'
        if 'slowroll' in low_name:
            return 'openSUSE_Slowroll'
        if 'leap:' in low_name:
            return image_name.split(':')[1]
        if any(x in low_name for x in ['fedora', 'rocky', 'centos']):
            return image_name.capitalize().replace(':', '_')
        return ""


CONTAINERS = [
    ContainerConfig(
        name="claude",
        naming_prefix="claude_code",
        image_platform="linux/amd64",
        image_name="debian:12",
        tz="Asia/Taipei",
        distro_pkgs=[],
        feature_presets=['zsh', 'qemacs'],
        nodejs=NodejsConfig(
            npm_global_pkgs=["@anthropic-ai/claude-code"]
        ),
        agent=AgentConfig(target_suffix="claude", command="npx claude", display_name="claude-code"),
    ),
    ContainerConfig(
        name="codex",
        naming_prefix="codex",
        image_platform="linux/amd64",
        image_name="debian:12",
        tz="Asia/Taipei",
        distro_pkgs=["links2"],
        feature_presets=['zsh', 'qemacs'],
        nodejs=NodejsConfig(
            npm_global_pkgs=["@openai/codex"]
        ),
        agent=AgentConfig(target_suffix="codex", command="npx codex"),
        publish_ports=["1455:1455/tcp"],
    ),
]


def _make_env(subdir: str, *, trim: bool = False) -> Environment:
    env = Environment(
        loader=FileSystemLoader([os.path.join(J2_ROOT, subdir), J2_ROOT]),
        keep_trailing_newline=True,
        trim_blocks=trim,
        lstrip_blocks=trim,
    )
    return env


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


def render_container(cfg: ContainerConfig) -> None:
    out = os.path.join(OUTPUT_DIR, cfg.name)
    # Clean previous output to avoid leftover files.
    if os.path.isdir(out):
        shutil.rmtree(out)

    docker_env = _make_env('docker')
    make_env = _make_env('make')
    zsh_env = _make_env('zsh', trim=True)
    bash_env = _make_env('bash', trim=True)

    _write(
        os.path.join(out, 'Makefile'),
        make_env.get_template('Makefile.j2').render(cfg=cfg),
    )
    _write(
        os.path.join(out, 'assets', 'Dockerfile'),
        docker_env.get_template('Dockerfile.j2').render(cfg=cfg),
    )

    for who in ('user', 'root'):
        _write(
            os.path.join(out, 'assets', 'dotfiles', who, '.zshrc'),
            zsh_env.get_template('.zshrc.j2').render(cfg=cfg, who=who),
        )
        _write(
            os.path.join(out, 'assets', 'dotfiles', who, '.bashrc'),
            bash_env.get_template('.bashrc.j2').render(cfg=cfg, who=who),
        )


def render_all() -> None:
    for cfg in CONTAINERS:
        render_container(cfg)
        print(f"Rendered {cfg.name} → {os.path.join(OUTPUT_DIR, cfg.name)}")


if __name__ == "__main__":
    render_all()
