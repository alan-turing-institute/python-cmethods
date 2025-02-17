#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfegerr
# Github: https://github.com/btschwertfeger
#

"""Module to to test the bias adjustment methods"""
import unittest
from typing import List, Tuple

import numpy as np
import pytest
import xarray as xr
from sklearn.metrics import mean_squared_error

from cmethods.CMethods import CMethods, UnknownMethodError


class TestMethods(unittest.TestCase):
    def setUp(self) -> None:
        obsh_add, obsp_add, simh_add, simp_add = self.get_datasets(kind="+")
        obsh_mult, obsp_mult, simh_mult, simp_mult = self.get_datasets(kind="*")

        self.data = {
            "+": {
                "obsh": obsh_add["+"],
                "obsp": obsp_add["+"],
                "simh": simh_add["+"],
                "simp": simp_add["+"],
            },
            "*": {
                "obsh": obsh_mult["*"],
                "obsp": obsp_mult["*"],
                "simh": simh_mult["*"],
                "simp": simp_mult["*"],
            },
        }

    def get_datasets(
        self,
        kind: str,
    ) -> Tuple[xr.Dataset, xr.Dataset, xr.Dataset, xr.Dataset]:
        historical_time = xr.cftime_range(
            "1971-01-01", "2000-12-31", freq="D", calendar="noleap"
        )
        future_time = xr.cftime_range(
            "2001-01-01", "2030-12-31", freq="D", calendar="noleap"
        )
        latitudes = np.arange(23, 27, 1)

        def get_hist_temp_for_lat(lat: int) -> List[float]:
            """Returns a fake interval time series by latitude value"""
            return 273.15 - (
                lat * np.cos(2 * np.pi * historical_time.dayofyear / 365)
                + 2 * np.random.random_sample((historical_time.size,))
                + 273.15
                + 0.1 * (historical_time - historical_time[0]).days / 365
            )

        def get_fake_hist_precipitation_data() -> List[float]:
            """Returns ratio based fake time series"""
            pr = (
                np.cos(2 * np.pi * historical_time.dayofyear / 365)
                * np.cos(2 * np.pi * historical_time.dayofyear / 365)
                * np.random.random_sample((historical_time.size,))
            )

            pr *= 0.0004 / pr.max()  # scaling
            years = 30
            days_without_rain_per_year = 239

            c = days_without_rain_per_year * years  # avoid rain every day
            pr.ravel()[np.random.choice(pr.size, c, replace=False)] = 0
            return pr

        def get_dataset(data, time, kind: str) -> xr.Dataset:
            """Returns a data set by data and time"""
            return (
                xr.DataArray(
                    data,
                    dims=("lon", "lat", "time"),
                    coords={"time": time, "lat": latitudes, "lon": [0, 1, 3]},
                )
                .transpose("time", "lat", "lon")
                .to_dataset(name=kind)
            )

        if kind == "+":
            some_data = [get_hist_temp_for_lat(val) for val in latitudes]
            data = np.array(
                [
                    np.array(some_data),
                    np.array(some_data) + 0.5,
                    np.array(some_data) + 1,
                ]
            )
            obsh = get_dataset(data, historical_time, kind=kind)
            obsp = get_dataset(data + 1, historical_time, kind=kind)
            simh = get_dataset(data - 2, historical_time, kind=kind)
            simp = get_dataset(data - 1, future_time, kind=kind)

        else:  # precipitation
            some_data = [get_fake_hist_precipitation_data() for _ in latitudes]
            data = np.array(
                [some_data, np.array(some_data) + np.random.rand(), np.array(some_data)]
            )
            obsh = get_dataset(data, historical_time, kind=kind)
            obsp = get_dataset(data * 1.02, historical_time, kind=kind)
            simh = get_dataset(data * 0.98, historical_time, kind=kind)
            simp = get_dataset(data * 0.09, future_time, kind=kind)

        return obsh, obsp, simh, simp

    def test_linear_scaling(self) -> None:
        """Tests the linear scaling method"""

        for kind in ("+", "*"):
            ls_result = CMethods().linear_scaling(
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                kind=kind,
            )
            assert isinstance(ls_result, xr.core.dataarray.DataArray)
            assert mean_squared_error(
                ls_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_variance_scaling(self) -> None:
        """Tests the variance scaling method"""
        kind = "+"
        vs_result = CMethods().variance_scaling(
            obs=self.data[kind]["obsh"][:, 0, 0],
            simh=self.data[kind]["simh"][:, 0, 0],
            simp=self.data[kind]["simp"][:, 0, 0],
            kind="+",
        )
        assert isinstance(vs_result, xr.core.dataarray.DataArray)
        assert mean_squared_error(
            vs_result, self.data[kind]["obsp"][:, 0, 0], squared=False
        ) < mean_squared_error(
            self.data[kind]["simp"][:, 0, 0],
            self.data[kind]["obsp"][:, 0, 0],
            squared=False,
        )

    def test_delta_method(self) -> None:
        """Tests the delta method"""

        for kind in ("+", "*"):
            dm_result = CMethods().delta_method(
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                kind=kind,
            )
            assert isinstance(dm_result, xr.core.dataarray.DataArray)
            assert mean_squared_error(
                dm_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_quantile_mapping(self) -> None:
        """Tests the quantile mapping method"""

        for kind in ("+", "*"):
            qm_result = CMethods().quantile_mapping(
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                n_quantiles=100,
                kind=kind,
            )
            assert isinstance(qm_result, xr.core.dataarray.DataArray)
            assert mean_squared_error(
                qm_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_detrended_quantile_mapping(self) -> None:
        """Tests the detrendeed quantile mapping method"""

        for kind in ("+", "*"):
            dqm_result = CMethods().quantile_mapping(
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                n_quantiles=100,
                kind=kind,
                detrended=True,
            )
            assert isinstance(dqm_result, xr.core.dataarray.DataArray)
            assert mean_squared_error(
                dqm_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_quantile_delta_mapping(self) -> None:
        """Tests the quantile delta mapping method"""

        for kind in ("+", "*"):
            qdm_result = CMethods().quantile_delta_mapping(
                obs=self.data[kind]["obsh"][:, 0, 0],
                simh=self.data[kind]["simh"][:, 0, 0],
                simp=self.data[kind]["simp"][:, 0, 0],
                n_quantiles=100,
                kind=kind,
            )

            assert isinstance(qdm_result, xr.core.dataarray.DataArray)
            assert mean_squared_error(
                qdm_result, self.data[kind]["obsp"][:, 0, 0], squared=False
            ) < mean_squared_error(
                self.data[kind]["simp"][:, 0, 0],
                self.data[kind]["obsp"][:, 0, 0],
                squared=False,
            )

    def test_3d_sclaing_methods(self) -> None:
        """Tests the scaling based methods for 3-dimentsional data sets"""

        kind = "+"
        for method in CMethods().SCALING_METHODS:
            result = CMethods().adjust_3d(
                method=method,
                obs=self.data[kind]["obsh"],
                simh=self.data[kind]["simh"],
                simp=self.data[kind]["simp"],
                kind=kind,
                goup="time.month",  # default
            )
            assert isinstance(result, xr.core.dataarray.DataArray)
            for lat in range(len(self.data[kind]["obsh"].lat)):
                for lon in range(len(self.data[kind]["obsh"].lon)):
                    assert mean_squared_error(
                        result[:, lat, lon],
                        self.data[kind]["obsp"][:, lat, lon],
                        squared=False,
                    ) < mean_squared_error(
                        self.data[kind]["simp"][:, lat, lon],
                        self.data[kind]["obsp"][:, lat, lon],
                        squared=False,
                    )

    def test_3d_distribution_methods(self) -> None:
        """Tests the distribution based methods for 3-dimentsional data sets"""

        for kind in ("+", "*"):
            for method in CMethods().DISTRIBUTION_METHODS:
                result = CMethods().adjust_3d(
                    method=method,
                    obs=self.data[kind]["obsh"],
                    simh=self.data[kind]["simh"],
                    simp=self.data[kind]["simp"],
                    n_quantiles=25,
                )
                assert isinstance(result, xr.core.dataarray.DataArray)
                for lat in range(len(self.data[kind]["obsh"].lat)):
                    for lon in range(len(self.data[kind]["obsh"].lon)):
                        assert mean_squared_error(
                            result[:, lat, lon],
                            self.data[kind]["obsp"][:, lat, lon],
                            squared=False,
                        ) < mean_squared_error(
                            self.data[kind]["simp"][:, lat, lon],
                            self.data[kind]["obsp"][:, lat, lon],
                            squared=False,
                        )

    def test_n_jobs(self) -> None:
        kind = "+"
        result = CMethods().adjust_3d(
            method="quantile_mapping",
            obs=self.data[kind]["obsh"],
            simh=self.data[kind]["simh"],
            simp=self.data[kind]["simp"],
            n_quantiles=25,
            n_jobs=2,
        )
        assert isinstance(result, xr.core.dataarray.DataArray)
        for lat in range(len(self.data[kind]["obsh"].lat)):
            for lon in range(len(self.data[kind]["obsh"].lon)):
                assert mean_squared_error(
                    result[:, lat, lon],
                    self.data[kind]["obsp"][:, lat, lon],
                    squared=False,
                ) < mean_squared_error(
                    self.data[kind]["simp"][:, lat, lon],
                    self.data[kind]["obsp"][:, lat, lon],
                    squared=False,
                )

    def test_get_available_methods(self) -> None:
        assert CMethods().get_available_methods() == [
            "linear_scaling",
            "variance_scaling",
            "delta_method",
            "quantile_mapping",
            "quantile_delta_mapping",
        ]

    def test_unknown_method(self) -> None:
        with pytest.raises(UnknownMethodError):
            CMethods.get_function("LOCI_INTENSITY_SCALING")

        kind = "+"
        with pytest.raises(UnknownMethodError):
            CMethods().adjust_3d(
                method="distribution_mapping",
                obs=self.data[kind]["obsh"],
                simh=self.data[kind]["simh"],
                simp=self.data[kind]["simp"],
                kind=kind,
            )

        with pytest.raises(UnknownMethodError):
            CMethods().pool_adjust(
                params=dict(
                    method="distribution_mapping",
                    obs=self.data[kind]["obsh"],
                    simh=self.data[kind]["simh"],
                    simp=self.data[kind]["simp"],
                    kind=kind,
                )
            )

    def test_not_implemented_methods(self) -> None:
        kind = "+"
        with pytest.raises(ValueError):
            CMethods.empirical_quantile_mapping(
                self.data[kind]["obsh"],
                self.data[kind]["simh"],
                self.data[kind]["simp"],
                n_quantiles=10,
            )

    def test_invalid_adjustment_type(self) -> None:
        kind = "+"
        with pytest.raises(ValueError):
            CMethods.linear_scaling(
                self.data[kind]["obsh"],
                self.data[kind]["simh"],
                self.data[kind]["simp"],
                kind="/",
            )
        with pytest.raises(ValueError):
            CMethods.variance_scaling(
                self.data[kind]["obsh"],
                self.data[kind]["simh"],
                self.data[kind]["simp"],
                kind="*",
            )
        with pytest.raises(ValueError):
            CMethods.delta_method(
                self.data[kind]["obsh"],
                self.data[kind]["simh"],
                self.data[kind]["simp"],
                kind="/",
            )
        with pytest.raises(ValueError):
            CMethods.quantile_mapping(
                self.data[kind]["obsh"],
                self.data[kind]["simh"],
                self.data[kind]["simp"],
                kind="/",
                n_quantiles=10,
            )
        with pytest.raises(ValueError):
            CMethods.quantile_delta_mapping(
                self.data[kind]["obsh"],
                self.data[kind]["simh"],
                self.data[kind]["simp"],
                kind="/",
                n_quantiles=10,
            )

    def test_get_pdf(self) -> None:
        assert (CMethods.get_pdf(np.arange(10), [0, 5, 11]) == np.array((5, 5))).all()

    def test_get_adjusted_scaling_factor(self) -> None:
        assert CMethods().get_adjusted_scaling_factor(10, 5) == 5
        assert CMethods().get_adjusted_scaling_factor(10, 11) == 10
        assert CMethods().get_adjusted_scaling_factor(-10, -11) == -10
        assert CMethods().get_adjusted_scaling_factor(-11, -10) == -10


if __name__ == "__main__":
    unittest.main()
