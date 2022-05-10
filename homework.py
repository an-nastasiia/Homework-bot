import logging
import sys
import os
import time
from http import HTTPStatus

from dotenv import load_dotenv
import requests as r
import telegram as t
try:
    from simplejson.errors import JSONDecodeError
except ImportError:
    from json.decoder import JSONDecodeError
from elasticsearch.exceptions import NotFoundError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s | Функция: %(funcName)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def send_message(bot, message) -> None:
    """Отправляет сообщение в Telegram-чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'Бот отправил в Telegram сообщение: {message}.')
    except Exception as send_error:
        logger.error(f'Не удалось отправить сообщение: {send_error}.')


def get_api_answer(current_timestamp) -> dict:
    """Если запрос успешный, возвращает ответ API типа данных Python."""
    params = {'from_date': current_timestamp}
    try:
        response = r.get(ENDPOINT, headers=HEADERS, params=params)
    except ConnectionError:
        msg = 'Не удалось получить ответ от API'
        logger.error(msg)
        raise ConnectionError(msg)
    if response.status_code == HTTPStatus.OK:
        try:
            return response.json()
        except JSONDecodeError:
            msg = 'Не удалось преобразовать JSON-ответ к типу данных Python'
            logger.error(msg)
            raise JSONDecodeError(msg)
    elif response.status_code == HTTPStatus.NOT_FOUND:
        msg = (f'Произошел сбой: эндпоинт {ENDPOINT} недоступен. '
               f'Код ответа API: {response.status_code}')
        logger.error(msg)
        raise NotFoundError(msg)
    else:
        msg = (f'Cбой при запросе к эндпоинту {ENDPOINT}. '
               f'Код ответа API: {response.status_code}')
        logger.error(msg)
        raise r.RequestException(msg)


def check_response(response) -> list:
    """Если ответ API корректен, возвращает список домашних работ."""
    if not isinstance(response, dict):
        msg = ('API прислал данные не в виде dict.')
        logger.error(msg)
        raise TypeError(msg)
    homework_list = response.get('homeworks')
    if not isinstance(homework_list, list):
        msg = ('По ключу homeworks данные пришли не в виде list.')
        logger.error(msg)
        raise TypeError(msg)
    else:
        return homework_list


def parse_status(homework) -> str:
    """Возвращает один из вердиктов словаря HOMEWORK_STATUSES."""
    try:
        homework_name = homework.get('homework_name')
    except type(homework) != dict:
        msg = f'Тип данных домашки {type(homework)}, а не dict.'
        logger.error(msg)
        raise TypeError(msg)
    except homework_name is None:
        msg = 'В словаре homework нет ключа homework_name.'
        logger.error(msg)
        raise KeyError(msg)
    verdict = HOMEWORK_STATUSES.get(homework.get('status'))
    if verdict is None:
        msg = ('Недокументированный статус домашней работы.')
        logger.error(msg)
        raise KeyError(msg)
    return (f'Изменился статус проверки работы "{homework_name}". {verdict}')


def check_tokens() -> bool:
    """Проверка доступности обязательных переменных окружения."""
    tokens = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
    global missing_tokens
    missing_tokens = []
    for token in tokens:
        if globals()[token] is None:
            missing_tokens.append(token)
    if len(missing_tokens) != 0:
        return False
    return True


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        msg = ('Нет обязательных переменных окружения: '
               f'{", ".join(missing_tokens)}. '
               'Программа принудительно остановлена.')
        logger.critical(msg)
        raise t.error.InvalidToken()
    bot = t.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    msg_error = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homework_list = check_response(response)
            if len(homework_list) == 0:
                logger.debug('Статус проверки не обновлялся.')
            else:
                for homework in homework_list:
                    message = parse_status(homework)
                    send_message(bot, message)
            current_timestamp = response.get('current_date', current_timestamp)
        except Exception as error:
            if error != msg_error:
                message = f'Произошел сбой: {error}'
                send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
