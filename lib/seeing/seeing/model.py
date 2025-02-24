import dask.array as da
import xarray
from numba import jit


class Model:

    def __init__(self, dataset):
        self.dataset = dataset

    def read(self, path, format="netcdf"):
        if format == "netcdf":
            self.dataset = xarray.open_dataset(path)
        else:
            raise ValueError("Format not supported")

    def write(self, path, format="netcdf"):
        if format == "netcdf":
            self.dataset.to_netcdf(path)
        else:
            raise ValueError("Format not supported")

    @jit
    def apply_function(data, function):
        return function(data)

    def apply(self, function):
        z_levels = self.dataset.z.values
        for z in z_levels:
            data = self.dataset.sel(z=z).data
            data = da.from_array(data, chunks="auto")
            data = data.map_blocks(self.apply_function, function=function)
            self.dataset.sel(z=z).data = data.compute()

    def compute_seeing(self):
        pass
