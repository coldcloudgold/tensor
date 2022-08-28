import click

from core.config import logger, settings
from core.utils import default_data_handlder, fetch_data, url_to_path, write_data


@click.command()
@click.argument("url")
@click.option("--main_dir/--no-main_dir", default=False)
def handle(url, main_dir):
    """Получение, обработка и запись данных.

    url — Адрес страницы

    --main_dir/--no-main_dir — Булев флаг. Если указан,
    то корневой директорией записи данных будет основная
    директория из файла конфигурации
    """

    logger.info("Начало обработки запроса")
    data = fetch_data(url)
    data = default_data_handlder.process_data(data)

    if main_dir:
        main_dir = settings.main_dir

    file = url_to_path(url, main_dir)

    if file and data:
        write_data(file, data)


if __name__ == "__main__":
    handle()
