# Install NajaEDA

Use the [shared Python environment](../README.md) and published binary wheel
`najaeda==0.7.24`, rather than compiling Naja or checking it out as a submodule.
The [published package](https://pypi.org/project/najaeda/0.7.24/) identifies supported
Python/platform wheels. The initial example uses Python 3.13.

```sh
. .venv/bin/activate
python -m pip install --only-binary=:all: 'najaeda==0.7.24'
python -c 'from importlib.metadata import version; from najaeda import netlist; print(version("najaeda")); print(netlist.__file__)'
```

If no compatible wheel is available, stop and report the platform/Python mismatch;
do not fall back to building from source. Do not set paths to an old source build
or mix it with a different Naja version: Kepler Formal 0.5.0 requires this exact
NajaEDA wheel version in the shared environment.
