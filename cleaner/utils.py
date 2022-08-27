from pathlib import Path
from typing import List, Optional
from xml.sax.xmlreader import AttributesNSImpl

import requests
from fake_useragent import UserAgent
from justext import get_stoplist
from justext.core import PARAGRAPH_TAGS, Cleaner, Paragraph
from justext.core import ParagraphMaker as DefaultParagraphMaker
from justext.core import classify_paragraphs, html_to_dom, is_blank, revise_paragraph_classification
from lxml.html import HtmlElement

from .config import logger, settings


def fetch_data(url: str, timeout: float = 2.0) -> Optional[str]:  # type: ignore[return]
    """Функция возвращает данные со страницы."""

    try:
        user_agent = UserAgent()
        response = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent.random})
        if response.status_code == 200:
            return response.content.decode(settings.default_encoding)

    except requests.exceptions.ReadTimeout:
        logger.error(f"Тайм-аут чтения ({timeout}) для {url}")

    except requests.exceptions.ConnectionError:
        logger.error(f"Тайм-аут коннекта ({timeout}) для {url}")

    except Exception as exc:
        logger.error(f"{exc.__class__.__name__}: {exc}")


def url_to_path(url: str, main_dir: str = None) -> Path:
    """Функция преобразует url в путь"""

    base_url, page = url.strip("/").rsplit("/", 1)
    site = base_url.split("//", 1)[1]

    if "html" in page:
        name, _ = page.split(".")
        filename = f"{name}.txt"
    else:
        filename = f"{page}.txt"

    return Path(main_dir or "", site, filename)


def create_path(path: Path):
    """Функция создает путь, если такой не существует."""

    path = Path(*path.parts[:-1])

    if not path.exists():
        try:
            path.mkdir()
        except FileNotFoundError:
            dirs = path.parts
            count_dirs = len(dirs)

            for index in range(1, count_dirs + 1):
                parent_dir = Path(*dirs[:index])

                if not parent_dir.exists():
                    parent_dir.mkdir()


def write_data(file: Path, data: str):
    """Функция записывает данные в файл."""

    create_path(file)

    with open(file, "w") as new_file:
        new_file.write(data)

    if file.exists():
        logger.info(f"Данные записаны: {file}")


class HTMLCleaner:
    """Класс отчистки HTML."""

    def __init__(
        self,
        default_encoding: str = settings.default_encoding,
        cleaning_settings: dict = settings.cleaning_settings,
    ):
        self._default_encoding = default_encoding
        self._cleaner = Cleaner(**cleaning_settings)

    def clean_html(self, html_text: str) -> HtmlElement:
        dom = html_to_dom(html_text, default_encoding=self._default_encoding)

        return self._cleaner.clean_html(dom)


default_cleaner = HTMLCleaner()


class ParagraphMaker(DefaultParagraphMaker):
    """Класс обработки данных DOM.

    Формирует список с параграфами.
    """

    tags = PARAGRAPH_TAGS

    def _get_url(self, attrs: AttributesNSImpl) -> Optional[str]:  # type: ignore[return]
        """Метод извлечения ссылки."""

        for item in attrs.items():
            if item[0][1] == "href":
                return item[1]

    def startElementNS(self, name, qname, attrs):
        """Метод обработки начала тэга."""

        name = name[1]
        self.path.append(name)

        if name in self.tags or (name == "br" and self.br):
            if name == "br":
                self.paragraph.tags_count -= 1

            self._start_new_pragraph()

        else:
            self.br = bool(name == "br")

            if self.br:
                self.paragraph.append_text(" ")

            elif name == "a":
                self.link = True
                self._url = self._get_url(attrs)

            self.paragraph.tags_count += 1

    def characters(self, content):
        """Метод обработки данных внутри тэга."""

        if is_blank(content):
            return

        text = self.paragraph.append_text(content)

        if self.link:
            self.paragraph.chars_count_in_links += len(text)
            if self._url:
                self.paragraph.append_text(f" [{self._url}]")
        self.br = False


class DataHandler:
    """Класс обработки данных."""

    def __init__(
        self,
        html_cleaner: HTMLCleaner = default_cleaner,
        paragraph_maker: DefaultParagraphMaker = ParagraphMaker,
    ):
        self._html_cleaner = html_cleaner
        self._paragraph_maker = paragraph_maker

    def process_data(
        self,
        html_text: str,
        stoplist: frozenset = get_stoplist(settings.classification_settings.language),
        length_low: int = settings.classification_settings.length_low,
        length_high: int = settings.classification_settings.length_high,
        stopwords_low: float = settings.classification_settings.stopwords_low,
        stopwords_high: float = settings.classification_settings.stopwords_high,
        max_link_density: float = settings.classification_settings.max_link_density,
        no_headings: bool = settings.classification_settings.no_headings,
        max_heading_distance: int = settings.classification_settings.max_heading_distance,
        max_length_line: int = settings.max_length_line,
    ) -> str:
        cleaned_html = self._html_cleaner.clean_html(html_text)
        paragraphs: List[Paragraph] = self._paragraph_maker.make_paragraphs(cleaned_html)
        classify_paragraphs(
            paragraphs=paragraphs,
            stoplist=stoplist,
            length_low=length_low,
            length_high=length_high,
            stopwords_low=stopwords_low,
            stopwords_high=stopwords_high,
            max_link_density=max_link_density,
            no_headings=no_headings,
        )
        revise_paragraph_classification(paragraphs, max_heading_distance=max_heading_distance)

        paragraphs_text = "\n".join([paragraph.text for paragraph in paragraphs if not paragraph.is_boilerplate])
        pretty_text = self._format_text(paragraphs_text, max_length_line=max_length_line)

        return pretty_text

    def _format_text(self, text: str, max_length_line: int = settings.max_length_line) -> str:
        """Метод обработки всего текста."""

        out_text = ""

        for paragraph in text.split("\n"):
            out_text += self._split_line(paragraph, max_length_line)

        out_text = out_text.strip()

        return out_text

    def _split_line(self, text: str, max_length_line) -> str:
        """Метод разбивки строки до указанной длинны."""

        length_line: int = 0
        out_text: str = ""
        words: list = text.split(" ")

        for number, word in enumerate(words):
            if number != 0:
                length_word = len(word) + 1  # пробел между словами

                if length_line + length_word <= max_length_line:
                    length_line += length_word
                    out_text += " " + word

                else:
                    length_line = length_word - 1  # пробела после переноса нет
                    out_text += "\n" + word

            else:
                length_line = len(word)
                out_text += word

        out_text += "\n\n"

        return out_text


default_data_handlder = DataHandler()
