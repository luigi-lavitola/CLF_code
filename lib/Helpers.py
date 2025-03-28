
def WAIT_UNTIL_TRUE(func):
    while True:
        try:
            ret = func()
        except:
            pass
        if ret:
            break


