# example of a race condition with a shared variable (Python 3.10+)
from time import sleep
from threading import Thread


# make additions into the global variable
def adder(amount, repeats):
    global value
    for _ in range(repeats):
        # copy the value
        tmp = value
        # suggest a context switch
        sleep(0)
        # change the copy
        tmp = tmp + amount
        # suggest a context switch
        sleep(0)
        # copy the value back
        value = tmp


# make subtractions from the global variable
def subtractor(amount, repeats):
    global value
    for _ in range(repeats):
        # copy the value
        tmp = value
        # suggest a context switch
        sleep(0)
        # change the copy
        tmp = tmp - amount
        # suggest a context switch
        sleep(0)
        # copy the value back
        value = tmp


# define the global variable
value = 0
# start a thread making additions
adder_thread = Thread(target=adder, args=(100, 1000000))
adder_thread.start()
# start a thread making subtractions
subtractor_thread = Thread(target=subtractor, args=(100, 1000000))
subtractor_thread.start()
# wait for both threads to finish
print("Waiting for threads to finish...")
adder_thread.join()
subtractor_thread.join()
# report the value
print(f"Value: {value}")
