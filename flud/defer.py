import traceback


class DefaultException(Exception):
    pass


class Failure:
    def __init__(self, value):
        if isinstance(value, Failure):
            self.value = value.value
        elif isinstance(value, BaseException):
            self.value = value
        else:
            self.value = Exception(str(value))

    def check(self, *error_types):
        for error_type in error_types:
            if isinstance(error_type, str):
                qualname = "%s.%s" % (
                    self.value.__class__.__module__,
                    self.value.__class__.__name__,
                )
                if qualname == error_type or self.value.__class__.__name__ == error_type:
                    return True
            elif isinstance(error_type, type) and isinstance(self.value, error_type):
                return True
        return False

    def getErrorMessage(self):
        return str(self.value)

    def getTraceback(self):
        return "".join(
            traceback.format_exception(
                type(self.value), self.value, self.value.__traceback__
            )
        )

    def __str__(self):
        return self.getErrorMessage()

    def __repr__(self):
        return "Failure(%r)" % (self.value,)


class Deferred:
    def __init__(self):
        self.called = False
        self._paused = False
        self._failed = False
        self._result = None
        self._callbacks = []

    def addCallbacks(
        self,
        callback,
        errback=None,
        callbackArgs=None,
        callbackKeywords=None,
        errbackArgs=None,
        errbackKeywords=None,
    ):
        self._callbacks.append(
            (
                callback,
                errback,
                callbackArgs or (),
                callbackKeywords or {},
                errbackArgs or (),
                errbackKeywords or {},
            )
        )
        if self.called and not self._paused:
            self._run_callbacks()
        return self

    def addCallback(self, callback, *args, **kwargs):
        return self.addCallbacks(
            callback,
            None,
            callbackArgs=args,
            callbackKeywords=kwargs,
        )

    def addErrback(self, errback, *args, **kwargs):
        return self.addCallbacks(
            None,
            errback,
            errbackArgs=args,
            errbackKeywords=kwargs,
        )

    def addBoth(self, callback, *args, **kwargs):
        return self.addCallbacks(
            callback,
            callback,
            callbackArgs=args,
            callbackKeywords=kwargs,
            errbackArgs=args,
            errbackKeywords=kwargs,
        )

    def callback(self, result):
        if self.called:
            raise RuntimeError("Deferred already fired")
        self.called = True
        self._failed = False
        self._result = result
        self._run_callbacks()
        return self

    def errback(self, error):
        if self.called:
            raise RuntimeError("Deferred already fired")
        self.called = True
        self._failed = True
        self._result = error if isinstance(error, Failure) else Failure(error)
        self._run_callbacks()
        return self

    def _continue(self, success, value):
        self._paused = False
        self._failed = not success
        self._result = value
        self._run_callbacks()

    def _run_callbacks(self):
        while self._callbacks and not self._paused:
            callback, errback, cb_args, cb_kwargs, eb_args, eb_kwargs = self._callbacks.pop(0)
            func = errback if self._failed else callback
            args = eb_args if self._failed else cb_args
            kwargs = eb_kwargs if self._failed else cb_kwargs
            if func is None:
                continue
            try:
                result = func(self._result, *args, **kwargs)
            except Exception as exc:
                self._failed = True
                self._result = Failure(exc)
                continue

            if isinstance(result, Deferred):
                self._paused = True

                def _resume_success(value):
                    self._continue(True, value)
                    return value

                def _resume_failure(error):
                    wrapped = error if isinstance(error, Failure) else Failure(error)
                    self._continue(False, wrapped)
                    return wrapped

                result.addCallbacks(_resume_success, _resume_failure)
                return

            if self._failed:
                if isinstance(result, Failure):
                    self._result = result
                else:
                    self._failed = False
                    self._result = result
            else:
                if isinstance(result, Failure):
                    self._failed = True
                    self._result = result
                else:
                    self._result = result


def succeed(result):
    deferred = Deferred()
    deferred.callback(result)
    return deferred


def fail(error):
    deferred = Deferred()
    deferred.errback(error)
    return deferred


class _FailureNamespace:
    DefaultException = DefaultException
    Failure = Failure


failure = _FailureNamespace()
