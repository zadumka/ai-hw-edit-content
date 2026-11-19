"""Text cleaning, identical to `to_plain_text` in the QA notebook `analytics (1).ipynb`."""
import html as html_lib
import re

from bs4 import BeautifulSoup
from markdown import markdown

HTML_TAG_PATTERN = re.compile(r'<(p|strong|a|ul|li|ol|br|code|em|div|span|h[1-6])\b', re.IGNORECASE)
MD_PATTERN = re.compile(r'(\*\*|__|##|\[.*?\]\(.*?\)|```|`[^`]+`)', re.MULTILINE)


def detect_format(text) -> str:
    text = str(text)
    if HTML_TAG_PATTERN.search(text):
        return 'html'
    if MD_PATTERN.search(text):
        return 'markdown'
    return 'plain'


def to_plain_text(text) -> str:
    text = str(text)
    fmt = detect_format(text)
    if fmt == 'markdown':
        text = markdown(text)
    if fmt in ('html', 'markdown'):
        text = html_lib.unescape(text)
        text = BeautifulSoup(text, 'html.parser').get_text(separator=' ')
    text = text.replace('-', '')
    return re.sub(r'\s+', ' ', text).strip()
