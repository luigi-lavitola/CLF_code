
def WAIT_UNTIL_TRUE(func):
    while True:
        ret = None
        try:
            ret = func()
        except:
            pass
        if ret:
            break


