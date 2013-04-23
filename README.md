## Belasitsa
=========

A _very_ simple WSGI back end for Mongrel 2.  It is less than 200 lines of code and easily adaptable.

### Dependencies:
* pyzmq
* gevent

### Usage:
```
belasitsa -s send -r recv -a module.app [-w nworkers]
```
where:
* send is a Mongrel 2 server's SUB socket to send responses to, for example ```-s 'tcp://127.0.0.1:6666'```
* recv is a Mongrel 2 server's PUSH socket to receive requests from, for example ```-r 'tcp://127.0.0.1:6667'```
* module.app is the location of your WSGI-compliant application.  If you would access your app in a python prompt with ```from your.wsgi.module import myapp```, then you would tell belasitsa ```-a your.wsgi.module.myapp```
* nworkers is the number of request handling greenlets to spawn.  Mongrel 2 will serve them in a round-robin fashion.  Defaults to 1.
