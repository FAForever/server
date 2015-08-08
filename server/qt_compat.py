import os

quamash_impl = os.environ.get('QUAMASH_QTIMPL')

if quamash_impl == 'PyQt5':
    from PyQt5 import QtCore
    from PyQt5 import QtNetwork
    from PyQt5 import QtSql
else:
    from PySide import QtCore
    from PySide import QtNetwork
    from PySide import QtSql

if not hasattr(QtCore, 'Signal'):
    QtCore.Signal = QtCore.pyqtSignal
