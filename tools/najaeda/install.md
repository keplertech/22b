# Install NajaEDA

Use the [shared Python environment](../README.md) and published binary wheel
`najaeda==0.7.20`, rather than compiling Naja or checking it out as a submodule.
The [published package](https://pypi.org/project/najaeda/0.7.20/) identifies supported
Python/platform wheels. The initial example uses Python 3.13.

```sh
. .venv/bin/activate
python -m pip install --only-binary=:all: 'najaeda==0.7.20'
python -c 'from importlib.metadata import version; from najaeda import netlist; print(version("najaeda")); print(netlist.__file__)'
```

If no compatible wheel is available, stop and report the platform/Python mismatch;
do not fall back to building from source. Do not set paths to an old source build
or assume Kepler's packaged Python runtime is this editing environment.
