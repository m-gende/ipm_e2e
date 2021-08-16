# Motivation

`AT-SPI` provides an api that we can use to write automated _end to
end_ tests that interact with the _graphical user interface_.  That's
great, but this api is a low-level api, that can be really cumbersome.
Let's take, as an example, the following user history:

```Gherkin
GIVEN I started the application
WHEN I click the button "Contar"
THEN I see the label "Has pulsado 1 vez"
```

When we implement that user history as a test using the bare at-spi,
we can get something like:

```python
# GIVEN I started the application

## Run it as a new OS process
path = "./contador.py"
name = f"{path}-test-{str(random.randint(0, 100000000))}"
process = subprocess.Popen([path, '--name', name])
assert process is not None, f"No pude ejecuar la aplicación {path}"

## Wait until at-spi founds it in the desktop
## Include a timeout
desktop = Atspi.get_desktop(0)
start = time.time()
timeout = 5
app = None
while app is None and (time.time() - start) < timeout:
    gen = filter(lambda child: child and child.get_name() == name,
                 (desktop.get_child_at_index(i) for i in range(desktop.get_child_count())))
    app = next(gen, None)
    if app is None:
        time.sleep(0.6)

## Check everything went ok
if app is None:
    process and process.kill()
    assert False, f"La aplicación {path} no aparece en el escritorio"

    
# WHEN I click the button "Contar"

## Search the button
for obj in tree_walk(app):
    if (obj.get_role_name() == 'push button' and
        obj.get_name() == 'Contar'):
        break
else:
    assert False, "No pude encontrar el botón 'Contar'"

## Search the action 'click'
for idx in range(obj.get_n_actions()):
    if obj.get_action_name(idx) == 'click':
        break
else:
    assert False, "El botón 'Contar' no tiene una acción 'click'"

## Perform the action
obj.do_action(idx)


# THEN I see the label "Has pulsado 1 vez"

## Search the label
for obj in tree_walk(app):
    if (obj.get_role_name() == 'label' and
        obj.get_text(0, -1).startswith("Has pulsado")):
        break
else:
    assert False, "No pude encontrar la etiqueta 'Has pulsado ...'"

## Check the text
assert obj.get_text(0, -1) == "Has pulsado 1 vez"


# Clean-up the mess & finish
process and process.kill()
```


As seen, using this api implies writing a lot of repetitive and
cumbersome code only to search for objects, getting their attributes,
performing actions on them, ...

After writing two or three tests, we'll probably find ourselves
writing a library to reuse this common code. And this is how the idea
of writing this library come in place the first time. But instead of
sticking around with just abstracting the repeated code, I wanted the
library to provide a more high-level api closer to the _gherkin
language_ than to the _c api_.

After implementing the same example using the library, we can get the
following code:

```python
# GIVEN I started the application
process, app = e2e.run("./contador.py")
## Check everything went ok
if app is None:
    process and process.kill()
    assert False, f"La aplicación {path} no aparece en el escritorio"
do, shows = e2e.perform_on(app)
   
# WHEN I click the button 'Contar'
do('click', role= 'push button', name= 'Contar')

# THEN I see the label "Has pulsado 1 vez"
assert shows(role= "label", text= "Has pulsado 1 vez")

# Clean-up the mess & finish
process and process.kill()
```
