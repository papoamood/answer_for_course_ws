Здравствуйте.

Были вопросы по "общению" между тредами (threads).

Попыталься дать развернутый ответ с примерами кода. 

# Введение

Сначала несколько вводных.
Допустим у нас есть главный тред с нашей торговой логикой и/или анализом данных.
У нас есть второй тред - где происходит подключение к websocket, десерелиазация (из строки или массива байт json -> в python объект).
Т.е. у нас две логические сущности работающие "параллельно" (тут большие кавычки :)).

Мы входим в очень непростую область - concurrency - т.е. организацию и корректное общение независимых и работающих одновременно сущностей.

Почему "параллельно" в кавычках?

Одновременно в программе может быть десятки тредов, но работать она будет и на одном процессоре. Каждому треду будет даватся квант времени на исполнение, потом просходит context switch, тред сохраняет свое состояние, управление передается другому и тд. Таким образом на физически одном процессоре визуально и на глаз как бы параллельно может работать несколько задач.

Из официальной документации :

Python implementation detail (тот python который все используют): In CPython, due to the Global Interpreter Lock, only one thread can execute Python code at once (even though certain performance-oriented libraries might overcome this limitation). If you want your application to make better use of the computational resources of multi-core machines, you are advised to use multiprocessing or concurrent.futures.ProcessPoolExecutor. However, threading is still an appropriate model if you want to run multiple I/O-bound tasks simultaneously.

Итак, выводы из этого:

1. Только один тред может испольнять код в один момент времени. Даже на нескольких ядрах. Т.е. истинной параллелизм используя Thread python невозможен, потому-что GIL (Global Interpreter Lock).

2. "Истинная" параллельность возможна используя несколько процессов (т.е. прямо процессов интерпретатора python, не путать с тредами) - модуль `multiprocessing` или `concurrent.futures.ProcessPoolExecutor` как абстракция над ним. Это когда требуются действительно тяжелые для CPU вычисления (cpu bound задачи). Это пока не наш случай.

3. Тем не менее модель тредов - это нормальная модель, когда наша задача - io bound, т.е. задача упирается во всякие запросы по сети, базы данных, прочие io. Для таких задач да - треды подходят. Как и прочие event loop, как и asyncio.



# Общение между тредами

Напомню у нас есть 2 треда - логика и websockets.
Главный тред - тред с логикой - принято называть MainThread, так и будем делать далее. Работа с вебсокетами - WebSocketThread.
Т.е. эти два треда - две сущности - крутятся независимо друг от друга.

В WebSocketThread когда запустилась функция `run_forever()` - установилось соединение и внутри уже этой функции запустился свой event loop - цикл обработки сообщений, всякая внутренняя вебсокет-машинерия и вызовы функций-колбеков для этих сообщений `on_message`, `on_error` и тд). В текущий момент WebSocketThread всегда (пока не разорвется соединение) внутри этого event loop - внутри функции `run_forever()`

Внутри `run_forever()` пришло сообщение от binance - библиотека сообщение обработала и вызвала нашу функцию-колбэк `on_message(ws_conn, message)`. Внутри нее мы преобразовали из json в python обьект (словарь или dict в нашем случае), взяли что нам нужно.

Куда и как это положить и передать в MainThread.

Казалось бы можно положить куда то в глобальную переменную или в какой-нибудь глобальный обьект типа `AllData.set_last_price_for_symbol(symbol_name, lastprice)`, что-то такое. Ну и прямо в `on_message` менять эту переменную или обращаться к обьекту `AllData`, а в MainThread - в цикле опрашивать глобальную переменную (или вызывать что-нибудь типа `AllData.get_last_price_for(symbol)`)

Так вот. Так делать **НЕЛЬЗЯ**. 

Потому что два треда могут одновременно обращаться к одной области памяти (переменную или обьект - неважно) - один прямо в моменте пишет в нее, другой читает прямо в моменте записи. Это приводит к race condition (состоянию гонки если вообще есть корректный перевод). Данные в любой момент могут "поехать", и очень-очень сложно будет понять в чем причина - если логика растет и/или много тредов. Вообщем это давняя боль в concurrency и в програмировании в целом. Даже учитывая GIL в python - data race может произойти в момент context switch треда, т.е. да, если не углубляясь даже учитывая GIL так **нельзя делать**.

# Что делать?

В случае с тредами у нас несколько вариантов - lock и queue - локи и очереди. `threading.Event()` сразу отбросим, не очень полезно в нашем случае. 

## threading.Lock

lock = threading.Lock() - это обьект, с помощью которого мы как-бы защищаем общую область памяти. Мы создаем один экзэмпляр `lock = threading.Lock()`, и все треды далее используют этот lock.

При обращении к общей области памяти (переменная любого типа) тред использует lock:

1. тред вызывает `lock.acquire()`, тем самым lock входит в состояние *locked*
2. делает с данными все что нужно
3. отпускает lock методом `lock.release()`

```python
lock = threading.Lock()

# захватываем lock
lock.acquire()
# читаем или пишем в общую область памяти
...
# отпускаем lock
lock.release()

print("Работаем дальше")
```

Также lock можно использовать как context manager
при выходе из блока with - `lock.release()` вызовется сам
тем самым меньше вероятность забыть вызвать `lock.release()`
```python
lock = threading.Lock()

# захватываем lock
with lock:
	# читаем или пишем в общую область памяти
	...

# при выходе из блока здесь уже lock отпущен -
# lock.release() вызвался автоматически
print("Работаем дальше")
```

Если лок locked - т.е. в состояний закрыт - у нас есть гарантии, что *только один тред в один момент времени* обращается к области памяти, которую мы "защищаем" локом. Если другие треды попытаются вызвать этот лок и обратиться к общей области памяти, а он в состоянии locked (т.е прямо сейчас другой тред уже взял лок и работает с общими данными), тред будет ждать (блокируется) пока лок не отпустят.



## queue - наше всё !.

Очереди.

[https://docs.python.org/3/library/queue.html](https://docs.python.org/3/library/queue.html)

Из официальной документации:

The queue module implements multi-producer, multi-consumer queues. **It is especially useful in threaded programming when information must be exchanged safely between multiple threads**. The Queue class in this module implements all **the required locking semantics**.

Т.е. очереди - это предпочитаемый и рекомендуемый способ общения между тредами. Семантика локов уже имплементирована в них. Т.е. они thread-safe и обьект очереди можно безопасно передавать и использовать между тредами.

Модуль очереди предоставляет несколько типов очередей:

- Queue: полнофункциональная очередь по принципу «первым пришел – первым вышел» (FIFO).
- SimpleQueue: очередь FIFO с меньшей функциональностью.
- LifoQueue: очередь «последним пришел — первым вышел» (LIFO или стэк).
- PriorityQueue: очередь с приоритетом.

Т.е. `queue` может создана и далее использоваться во всех необходимых тредах.

    queue = Queue() # создаем очередь

Например, в WebSocketThread мы кладем в очередь нужную нам информацию в on_message:

```python
def on_message(self, _ws_app, msg):
    # преобразовали из json в dict
    data = json.loads(msg)

    # делаем что-то с данными и кладем в очередь
    ...
    queue.put(some_data)

...
# в MainThread - в цикле берем из очереди и делаем логику
# расчетов/торговли
while True:
	# берем данные из очереди
	some_data_from_queue = queue.get()
    	# делаем свою логику и переходим в начало цикла
    	...
    	# к слову здесь можно проверять длину нашей очереди
    	# queue.qsize()
    	# для того чтобы понять - успеваем ли мы в нашем
    	# MainThread обрабатывать сообщения, если очередь постоянно растет -
	# значит мы не успеваем, тут уже нужно думать об оптимизации нашей
	# логики и пр. 
```

# Заключение

В архиве с примерами будет файл `example_race_condition.py`. Это явная иллюстрация race conditions для Python 3.10+, попробуйте запустить несколько раз, вы получите разные результаты, хотя по логике - результат должен быть всегда один.

Пример с очередями в файле `queue_example.py`. Почитайте код и комментарии, думаю подход понятен.

Ссылки на почитать:

- [https://docs.python.org/3/library/threading.html](https://docs.python.org/3/library/threading.html)
- [https://docs.python.org/3/library/queue.html](https://docs.python.org/3/library/queue.html)
- [How to Share Variables Between Threads in Python](https://superfastpython.com/thread-share-variables/)
- [Race Condition With a Shared Variable in Python](https://superfastpython.com/thread-race-condition-shared-variable/)
- [Threading Mutex Lock in Python](https://superfastpython.com/thread-mutex-lock/)
