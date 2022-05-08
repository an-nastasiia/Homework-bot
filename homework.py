import logging
import sys
import os
import time
from http import HTTPStatus

from dotenv import load_dotenv
import requests as r
import telegram as t


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
logger.setLevel(logging.INFO)
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
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    response = r.get(ENDPOINT, headers=HEADERS, params=params)
    if response.status_code == HTTPStatus.OK:
        return response.json()
    elif response.status_code == HTTPStatus.NOT_FOUND:
        msg = (f'Произошел сбой: эндпоинт {ENDPOINT} недоступен. '
               f'Код ответа API: {response.status_code}')
        logger.error(msg)
        raise r.RequestException(msg)
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
    elif homework_list == {}:
        msg = ('API прислал пустой словарь.')
        logger.error(msg)
        raise KeyError(msg)
    elif response.get('homeworks') is None:
        msg = ('Ответ от API не содержит ключа "homeworks"')
        logger.error(msg)
        raise KeyError(msg)
    else:
        return homework_list


def parse_status(homework: dict) -> str:
    """Возвращает один из вердиктов словаря HOMEWORK_STATUSES"""
    homework_name = homework.get('homework_name')
    verdict = HOMEWORK_STATUSES.get(homework.get('status'))
    if verdict is None:
        msg = ('Недокументированный статус домашней работы.')
        logger.error(msg)
        raise KeyError(msg)
    return (f'Изменился статус проверки работы "{homework_name}". {verdict}')


def check_tokens() -> bool:
    """Проверка доступности обязательных переменных окружения."""
    tokens = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
    for token in tokens:
        if globals()[token] is None:
            return False
    return True


def main() -> None:
    """Основная логика работы бота."""
    bot = t.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    current_status = ''
    msg_error = ''
    if check_tokens():
        while True:
            try:
                response = get_api_answer(current_timestamp)
                homework_list = check_response(response)
                if homework_list:
                    for homework in homework_list:
                        message = parse_status(homework)
                        hw_status = homework.get('status')
                        if hw_status != current_status:
                            send_message(bot, message)
                            current_status = hw_status
                            current_timestamp = response.get('current_date',
                                                             current_timestamp)
                        else:
                            logger.debug('Статус проверки не обновлялся.')
                    time.sleep(RETRY_TIME)
            except Exception as error:
                if error != msg_error:
                    message = f'Произошел сбой: {error}'
                    send_message(bot, message)
                    time.sleep(RETRY_TIME)
    else:
        msg = ('Нет обязательной переменной окружения. '
               'Программа принудительно остановлена.')
        logger.critical(msg)
        raise t.InvalidToken(msg)


if __name__ == '__main__':
    main()
