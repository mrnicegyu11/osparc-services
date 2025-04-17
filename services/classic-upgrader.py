#!/usr/bin/env -S uv --quiet run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
# "jinja2", "pyyaml", "pydantic>2.0.0",
# "typer", "tqdm"
# ]
# ///
from pathlib import Path
import json
from typing import Any, Optional, Union, List
import typer
from pydantic import BaseModel, Field, validator
from jinja2 import Environment, FileSystemLoader, select_autoescape

app = typer.Typer(help="Docker Compose Parser and Template Generator")

class ServiceKey(BaseModel):
    key: str

class ServiceVersion(BaseModel):
    version: str

class ServiceType(BaseModel):
    type: str

class Author(BaseModel):
    name: str
    email: str
    affiliation: str

class ServiceAuthors(BaseModel):
    authors: List[Author]

class ServiceSettingsItem(BaseModel):
    name: str
    type: str
    value: Union[dict, int, str, List[str]]

from typing import Any, Optional, Union, List
from pydantic import BaseModel, Field, field_validator
import yaml

# 1. Define nested build configuration model
class BuildConfig(BaseModel):
    context: str
    dockerfile: str
    target: str
    labels: dict[str, str] = Field(default_factory=dict)

# 2. Enhanced service model with build labels
class EnhancedService(BaseModel):
    image: str
    build: BuildConfig  # Use nested model instead of dict
    environment: list[str]
    ports: list[str]

    # Special fields for parsed build labels
    service_key: Optional[dict] = Field(None, alias="io.simcore.key")
    service_version: Optional[dict] = Field(None, alias="io.simcore.version")
    # Add other label fields as needed...

    @field_validator("*", mode="before")
    @classmethod
    def parse_build_labels(cls, value, info):
        if info.field_name.startswith("service_"):
            label_name = info.field_name.replace("_", ".", 1)
            if label_name in cls.model_fields:
                raw_value = value.build.labels.get(label_name)
                if raw_value:
                    return json.loads(raw_value)
        return value

# 3. Full compose model
class EnhancedComposeSpecification(BaseModel):
    version: str
    services: dict[str, EnhancedService]

# 4. Custom parser function
def parse_compose(file_path: str) -> EnhancedComposeSpecification:
    with open(file_path) as f:
        raw_data = yaml.safe_load(f)
    return EnhancedComposeSpecification.model_validate(raw_data)

# Usage in Typer commands remains similar, but access labels via:
# service.build.labels for raw labels
# service.service_key for parsed labels

@app.command()
def parse(
    input_path: Path = typer.Argument(..., exists=True, help="Path to docker-compose.yml"),
    output_path: Path = typer.Option(None, help="Output path for parsed JSON"),
):
    """Parse docker-compose file and show/output structured data"""
    try:
        compose_data = parse_compose(str(input_path))
        json_data = compose_data.json(indent=2)
        
        if output_path:
            output_path.write_text(json_data)
            typer.echo(f"Successfully saved parsed data to {output_path}")
        else:
            typer.echo_json(json.loads(json_data))
            
    except Exception as e:
        typer.secho(f"Error parsing compose file: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command()
def render_template(
    template_path: Path = typer.Argument(..., exists=True, help="Jinja2 template file"),
    compose_path: Path = typer.Option(None, exists=True, help="Path to docker-compose.yml"),
    json_path: Path = typer.Option(None, exists=True, help="Path to parsed JSON data"),
    output_path: Path = typer.Option(None, help="Output file path"),
):
    """Render a Jinja2 template using parsed compose data"""
    try:
        if compose_path and json_path:
            raise ValueError("Specify either compose_path or json_path, not both")
        
        if compose_path:
            compose_data = parse_compose(str(compose_path))
        elif json_path:
            compose_data = EnhancedComposeSpecification.parse_file(json_path)
        else:
            raise ValueError("Must provide either compose_path or json_path")

        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            autoescape=select_autoescape()
        )
        template = env.get_template(template_path.name)
        
        service = compose_data.services["tissue-properties"]
        rendered = template.render(
            service=service,
            version=service.service_version.version if service.service_version else "",
            settings=service.service_settings,
            authors=service.labels.get("io.simcore.authors", "")
        )
        
        if output_path:
            output_path.write_text(rendered)
            typer.echo(f"Template rendered to {output_path}")
        else:
            typer.echo(rendered)
            
    except Exception as e:
        typer.secho(f"Template rendering failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

@app.command()
def show_labels(
    service_name: str = typer.Argument(..., help="Name of the service to inspect"),
    compose_path: Path = typer.Argument(..., exists=True, help="Path to docker-compose.yml"),
):
    """Show available labels for a service"""
    try:
        compose_data = parse_compose(str(compose_path))
        service = compose_data.services[service_name]
        
        typer.echo(f"Available labels for {service_name}:")
        for label_name in service.build.labels.keys():
            typer.echo(f"  - {label_name}")
            
    except KeyError:
        typer.secho(f"Service '{service_name}' not found", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
