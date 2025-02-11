# About
Create widgets and self-contained apps for [Jupyterlab](https://jupyterlab.readthedocs.io/en/latest/#)
written entirely in Python.

`Menubox` is the base class and can be used as is or can be subclassed to define
a new widget class. It is an Ipylab `Panel` widget combined with a HasParent widget.
Functionality includes:

* capable of loading multiple views
* minimizing
* moving itself inside a `showbox` and removing itself
* Button to close itself
* Buttons can be enabled/disabled on demand
* Can add itself to the shell (as can any ipylab Panel widget)

![filesystem](/docs/assets/filesystem.png)

 `MenuboxVT` provides additional features such as:

* observing nested values
* copying settings
* data persistence


## Installation

`menubox` relies on patched un-released versions of `Ipylab` and `Ipywidgets`
(including `jupyterlab-widget`), compatible wheels are stored in the `pkg` directory.
To ensure the packaged wheels are used, `menubox` should be installed from **source**
in editable mode.

```sh
# Obtain the source.
git clone https://github.com/fleming79/menubox

cd menubox

# Install in editable mode
pip install -e .
```

## Development

```sh
pip install -e .[dev]
```

### Vscode

Run configurations are provided for debugging.

## Distribution

```sh
hatch build -t sdist
# Only the source distribution is relevant (file ending in '.tar.gz')
```

Note: if the build doesn't start, try deleting the environment with.

```sh
hatch env remove
```


## License

`menubox` is distributed under the terms of the [MIT](LICENSE) license.

### Documentation:

For the moment, check out [`menubox.filesystem.Filesystem`](https://github.com/fleming79/menubox/blob/main/src/menubox/filesystem.py#L29) for an example.

TODO:

- Documentation [hints](https://learn.scientific-python.org/development/tutorials/docs/)
- or possibly https://squidfunk.github.io/mkdocs-material/
