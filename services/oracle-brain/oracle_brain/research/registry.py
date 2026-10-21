"""Industry source register; JSON-compatible YAML so no parser dependency is required."""
from dataclasses import dataclass
from datetime import timedelta
import json
from urllib.parse import urlsplit
from pathlib import Path

CADENCES = {'weekly': timedelta(days=7), 'quarterly': timedelta(days=91)}
ACCESS = {'public', 'licensed', 'member'}


@dataclass(frozen=True)
class Source:
    source_id: str
    publisher: str
    url: str
    jurisdiction: str
    scope: str
    access: str
    cadence: str
    enabled: bool = True
    rights_confirmed: bool = False

    def __post_init__(self):
        for name in ('source_id', 'publisher', 'url', 'jurisdiction', 'scope', 'access', 'cadence'):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f'{name} must be a nonempty string')
        for name in ('enabled', 'rights_confirmed'):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f'{name} must be a bool')
        if self.cadence not in CADENCES:
            raise ValueError(f'unknown cadence {self.cadence!r}')
        if self.access not in ACCESS:
            raise ValueError(f'unknown access {self.access!r}')
        try:
            parts = urlsplit(self.url)
            valid_url = (parts.scheme == 'https' and parts.hostname and
                         parts.port in (None, 443) and not parts.username and not parts.password)
        except ValueError:
            valid_url = False
        if not valid_url or any(ord(char) <= 32 or ord(char) == 127 for char in self.url):
            raise ValueError('source url must be an uncredentialed https destination')

    @property
    def interval(self) -> timedelta:
        return CADENCES[self.cadence]

    @property
    def authorized(self) -> bool:
        """Paid/member sources need existing rights; otherwise they are a coverage gap."""
        from .rights import is_authorized
        return is_authorized(self)


def parse_register(text: str) -> tuple[Source, ...]:
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
    except ImportError:
        data = json.loads(text)
    if type(data) is not dict or set(data) != {'sources'} or type(data['sources']) is not list:
        raise ValueError('register must contain a sources list')
    sources_list = []
    for row in data['sources']:
        if type(row) is not dict:
            raise ValueError('source record must be an object')
        try:
            sources_list.append(Source(**row))
        except TypeError as error:
            raise ValueError('source record has missing or unknown fields') from error
    sources = tuple(sources_list)
    ids = [s.source_id for s in sources]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate source_id')
    return sources


def load_register(path: Path) -> tuple[Source, ...]:
    return parse_register(Path(path).read_text(encoding='utf-8'))
