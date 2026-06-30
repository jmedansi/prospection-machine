try:
    import jinja2
    print(jinja2.__version__)
except Exception as e:
    print('ERROR', type(e).__name__, e)
