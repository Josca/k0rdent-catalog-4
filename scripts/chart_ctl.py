import yaml
import argparse
from jinja2 import Template
import os
import subprocess
import pathlib


chart_app_tpl = """apiVersion: v2
name: {{ name }}
description: A Helm chart that references the official "{{ name }}" Helm chart.
type: application
version: {{ version }}
dependencies:
{%- for dep in dependencies %}
  - name: {{ dep.name }}
    version: {{ dep.version }}
    repository: {{ dep.repository }}
{% endfor %}
"""


def read_charts_cfg(app: str, allow_return_none: bool = False) -> dict:
    helm_config_path = f"apps/{app}/charts/st-charts.yaml"
    if not os.path.exists(helm_config_path):
        if allow_return_none:
            return None
        raise Exception(f"{helm_config_path} file not found")
    with open(helm_config_path, "r", encoding='utf-8') as file:
        cfg = yaml.safe_load(file)
    return cfg


def generate_charts(app: str, cfg: dict):
    generate_app_chart(app, cfg)


def try_generate_lock_file(chart_dir: str) -> bool:
    chart_path = pathlib.Path(chart_dir)
    lock_file = chart_path / "Chart.lock"
    if lock_file.exists():
        return False
    subprocess.run(["helm", "dependency", "update", str(chart_path)], check=True)
    if not lock_file.exists():
        raise RuntimeError("helm dependency update ran, but Chart.lock was not created")
    return True


def generate_app_chart(app: str, cfg: dict):
    if cfg.get('service_template_only', False):
        return
    folder_path = try_create_chart_folders(app, cfg['name'], cfg['version'], False)
    chart = Template(chart_app_tpl).render(**cfg)
    with open(f"{folder_path}/Chart.yaml", "w", encoding='utf-8') as f:
        f.write(chart)
    try_generate_lock_file(folder_path)


def try_create_chart_folders(app: str, name: str, version: str, templates: bool) -> str:
    chart_path = f"apps/{app}/charts/{name}-{version}"
    if not os.path.exists(chart_path):
        os.makedirs(chart_path)
    if templates:
        templates_path = f"{chart_path}/templates"
        if not os.path.exists(templates_path):
            os.makedirs(templates_path)
    return chart_path


def generate(args: str):
    app = args.app
    cfg = read_charts_cfg(app)
    for chart in cfg['st-charts']:
        generate_charts(app, chart)


def get_last_deps(cfg: dict):
    last_deps = dict()
    for chart in cfg['st-charts']:
        for dep in chart['dependencies']:
            last_deps[dep['name']] = dep
    return last_deps


def check_updates(args: str):
    app = args.app
    cfg = read_charts_cfg(app, allow_return_none=True)
    if cfg is None:
        print('Charts config not found.')
        return
    last_deps = get_last_deps(cfg)
    for chart, data in last_deps.items():
        if not data['repository'].startswith("https"):
            print(f"Unsupported repo '{data['repository']}' to automatically check updates, skipping.")
            continue
        subprocess.run(["helm", "repo", "add", chart, data['repository']], check=True)
        subprocess.run(["helm", "repo", "update"], check=True)
        result = subprocess.run(["helm", "show", "chart", f"{chart}/{chart}"], check=True, capture_output=True, text=True)
        up_to_date_chart = yaml.safe_load(result.stdout)
        print(f"Last version found: {up_to_date_chart['version']}")
        if up_to_date_chart['version'] != data['version']:
            print(f"::warning::Update found for '{chart}': {data['version']} -> {up_to_date_chart['version']}")


parser = argparse.ArgumentParser(description='Catalog charts CLI tool.',
                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter)  # To show default values in help.
subparsers = parser.add_subparsers(dest="command", required=True)

show = subparsers.add_parser("generate", help="Generate charts from config")
show.add_argument("app")
show.set_defaults(func=generate)

check_upd = subparsers.add_parser("check-updates", help="Generate charts from config")
check_upd.add_argument("app")
check_upd.set_defaults(func=check_updates)

args = parser.parse_args()
args.func(args)
