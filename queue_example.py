import json
import pprint
import threading
import time
from queue import Queue

import websocket

# создаем очередь
# прямо в глобальной области видимости
# тем самым мы можем использовать переменную queue
# в колбэках
queue = Queue()

# создаем dict для хранения данных последних цен.
# используем только из MainThread после получения данных из очереди.
sym_to_price_map: dict[str, float] = {}


# Подготавливаем наши функции-обработчики для WebSocketApp обьекта.
# Все эти функции будут работать в отдельном треде - WebSocketThread (его мы создадим ниже).
# Как это работает.
# Мы создадим тред WebSocketThread и передадим треду функцию run_forever, которую он запустит.
# Потом мы запустим тред WebSocketThread.start().
# Внутри вновь созданного треда, когда в нем запустится функция run_forever() -
# установится соединение и внутри уже этой функции run_forever запустился свой event loop -
# цикл обработки сообщений, всякая внутренняя вебсокет-машинерия и вызовы
# функций-колбеков для этих сообщений on_message, on_error и тд
#
# Внутри функции run_forever() пришло сообщение от binance -
# библиотека сообщение обработала и вызвала нашу функцию-колбэк
# on_message(_wsapp, message). Внутри нее мы преобразовали из
# json в python обьект (словарь или dict в нашем случае), и просто передадим в очередь.
def on_message(_wsapp, message):
    # К слову бибилотека ожидает именно такие сигнатуры функций, как
    # в этом файле, удалять аргументы нельзя (они позционные) и функция
    # не должна ничего возвращать (формально говоря она возвращает None).
    # Если мы не используем аргументы (как в нашем случае) просто называйте
    # их с _ в начале.

    # из json в dict
    parsed = json.loads(message)

    # Кладем в очередь.
    # Напоминаю, мы внутри функции on_message и она будет вызываться внутри треда WebSocketThread.
    # Но да, queue можно безопасно так просто использовать из другого треда, поскольку
    # семантика локов уже имплементирована в очередях.
    queue.put(parsed)


def on_ping(_wsapp, message):
    # По поводу того, как binance поддерживает websocket соединение.
    # Из доков binance:
    # The websocket server will send a ping frame every 5 minutes.
    # If the websocket server does not receive a pong frame back from the connection
    # within a 15 minute period, the connection will be disconnected.
    # Unsolicited pong frames are allowed.
    # Т.е. каждые 5 минут binance посылает нам ping frame и если binance server не получит
    # pong frame в ответ в течении 15ти минут - сервер binance закроет соединение со
    # своей стороны.
    # Библиотека сама обрабатывает ping frame и сама отсылает в ответ pong frame,
    # после этого вызывает этот колбэк on_ping. Т.е. при вызове этого колбэка pong уже отправлен.
    # Binance посылает пинги с пустым payload'ом, поэтому message будет пустым.
    print(
        f"Got a ping! A pong reply has already been automatically sent. Ping msg is {message}"
    )


# Остальные колбэки
def on_error(_wsapp, error):
    # error - это исключение при ошибке
    print(f"Error: {error}")


def on_close(_wsapp, close_status_code, close_msg):
    if close_status_code is not None and close_msg is not None:
        print(
            f"Close connection by server, status {close_status_code}, close message {close_msg}"
        )
    else:
        print("Close connection by error")


def on_open(_wsapp):
    print("Connection opened")


if __name__ == "__main__":
    list_streams = [
        "ethusdt@kline_1m",
        "btcusdt@kline_1m",
        "adausdt@kline_1m",
    ]

    url = f'wss://stream.binance.com:443/stream?streams={"/".join(list_streams)}'

    # Подготавливаем обьект WebSocketApp, передаем подготовленные url и колбэки
    websocket_app = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_ping=on_ping,
        on_close=on_close,
        on_error=on_error,
        on_open=on_open,
    )

    # Подготавливаем обьект WebSocketThread - обьект треда.
    # Обратите внимание мы передаем именно саму функцию, а не её вызов
    # нет скобок
    WebSocketThread = threading.Thread(target=websocket_app.run_forever)

    # Запускаем WebSocketThread
    WebSocketThread.start()

    # В данной строчке WebSocketThread запущен и работает в фоне.
    # Мы же до сих пор в нашем основном MainThread.

    # Запускаем постоянный цикл
    while True:
        # И здесь мы в нашем основном MainThread.

        # Получаем из очереди dict
        # Если очередь пуста - MainThread ждет (блокируется)
        from_queue = queue.get()

        try:
            symbol_name = from_queue["data"]["k"]["s"]
            price = float(
                from_queue["data"]["k"]["c"]
            )  # close price aka последняя цена
        except KeyError:
            # Обрабатываем исключение, когда dict из очереди не будет содержать ключей,
            # использованных в блоке try (["data"]["k"]["s"] или ["data"]["k"]["c"])
            # если ключей нет - продолжаем цикл.
            # Просто для примера.
            continue

        # Кладем в наш dict и печатаем его
        # Напоминаю, мы все еще в MainThread и sym_to_price_map создана в нем,
        # поэтому это обращение безопасно.
        sym_to_price_map[symbol_name] = price
        pprint.pprint(sym_to_price_map)

        # Здесь мы уже делаем свою логику торговли/анализа.
        # К слову также здесь можно проверять длину нашей очереди -
        # queue.qsize()
        # для того чтобы понять - успеваем ли мы в нашем
        # MainThread обрабатывать сообщения, если очередь постоянно растет -
        # значит мы не успеваем и уже нужно думать об оптимизации нашей
        # логики и пр.

        # В конце цикла, после нашей логики.
        # Есть мнение, что добавление time.sleep(0.001) - 1 миллисекунда -
        # помогает context switch'у на всяких windows системах, т.е.
        # помогаем передать управление WebSocketThread
        time.sleep(0.001)

    # До этой строчки мы не дойдем, поскольку вечный цикл выше, но
    # Такой способ заблокироваться в MainThread и ждать когда WebSocketThread
    # завершится. Не наш случай, но просто для примера.
    WebSocketThread.join()
