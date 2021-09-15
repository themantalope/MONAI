# Copyright 2020 - 2021 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import unittest

import numpy as np
import torch
from ignite.engine import Engine

from monai.data import CacheDataset, DataLoader, create_test_image_3d, decollate_batch
from monai.engines.utils import IterationEvents
from monai.handlers import TransformInverter
from monai.transforms import (
    AddChanneld,
    CastToTyped,
    Compose,
    CopyItemsd,
    LoadImaged,
    Orientationd,
    RandAffined,
    RandAxisFlipd,
    RandFlipd,
    RandRotate90d,
    RandRotated,
    RandZoomd,
    ResizeWithPadOrCropd,
    ScaleIntensityd,
    Spacingd,
    ToTensord,
)
from monai.utils.misc import set_determinism
from tests.utils import make_nifti_image

KEYS = ["image", "label"]


class TestTransformInverter(unittest.TestCase):
    def test_invert(self):
        set_determinism(seed=0)
        im_fname, seg_fname = [make_nifti_image(i) for i in create_test_image_3d(101, 100, 107, noise_max=100)]
        transform = Compose(
            [
                LoadImaged(KEYS),
                AddChanneld(KEYS),
                Orientationd(KEYS, "RPS"),
                Spacingd(KEYS, pixdim=(1.2, 1.01, 0.9), mode=["bilinear", "nearest"], dtype=np.float32),
                ScaleIntensityd("image", minv=1, maxv=10),
                RandFlipd(KEYS, prob=0.5, spatial_axis=[1, 2]),
                RandAxisFlipd(KEYS, prob=0.5),
                RandRotate90d(KEYS, spatial_axes=(1, 2)),
                RandZoomd(KEYS, prob=0.5, min_zoom=0.5, max_zoom=1.1, keep_size=True),
                RandRotated(KEYS, prob=0.5, range_x=np.pi, mode="bilinear", align_corners=True),
                RandAffined(KEYS, prob=0.5, rotate_range=np.pi, mode="nearest"),
                ResizeWithPadOrCropd(KEYS, 100),
                ToTensord("image"),  # test to support both Tensor and Numpy array when inverting
                CastToTyped(KEYS, dtype=[torch.uint8, np.uint8]),
                CopyItemsd("label", times=2, names=["label_inverted1", "label_inverted2"]),
                CopyItemsd("image", times=2, names=["image_inverted1", "image_inverted2"]),
            ]
        )
        data = [{"image": im_fname, "label": seg_fname} for _ in range(12)]

        # num workers = 0 for mac or gpu transforms
        num_workers = 0 if sys.platform == "darwin" or torch.cuda.is_available() else 2

        dataset = CacheDataset(data, transform=transform, progress=False)
        loader = DataLoader(dataset, num_workers=num_workers, batch_size=5)

        # set up engine
        def _train_func(engine, batch):
            self.assertTupleEqual(batch["image"].shape[1:], (1, 100, 100, 100))
            engine.state.output = engine.state.batch = decollate_batch(batch)
            engine.fire_event(IterationEvents.MODEL_COMPLETED)
            return engine.state.output

        engine = Engine(_train_func)
        engine.register_events(*IterationEvents)

        # set up testing handler
        TransformInverter(
            transform=transform,
            output_keys=["image_inverted1", "label_inverted1"],
            batch_keys="label",
            meta_keys=["image_inverted1_meta_dict", "label_inverted1_meta_dict"],
            batch_meta_keys="label_meta_dict",
            nearest_interp=True,
            to_tensor=[True, False],
            device="cpu",
        ).attach(engine)

        # test different nearest interpolation values
        TransformInverter(
            transform=transform,
            output_keys=["image_inverted2", "label_inverted2"],
            batch_keys="image",
            meta_keys=None,
            batch_meta_keys="image_meta_dict",
            meta_key_postfix="meta_dict",
            nearest_interp=[True, False],
            post_func=[lambda x: x + 10, lambda x: x],
        ).attach(engine)

        engine.run(loader, max_epochs=1)
        set_determinism(seed=None)

        for output in engine.state.output:
            self.assertTupleEqual(output["image"].shape, (1, 100, 100, 100))
            self.assertTupleEqual(output["label"].shape, (1, 100, 100, 100))
            # check the nearest inerpolation mode
            i = output["image_inverted1"]
            torch.testing.assert_allclose(i.to(torch.uint8).to(torch.float), i.to(torch.float))
            self.assertTupleEqual(i.shape, (1, 100, 101, 107))
            i = output["label_inverted1"]
            np.testing.assert_allclose(i.astype(np.uint8).astype(np.float32), i.astype(np.float32))
            self.assertTupleEqual(i.shape, (1, 100, 101, 107))

            # check the case that different items use different interpolation mode to invert transforms
            d = output["image_inverted2"]
            # if the interpolation mode is nearest, accumulated diff should be smaller than 1
            self.assertLess(torch.sum(d.to(torch.float) - d.to(torch.uint8).to(torch.float)).item(), 1.0)
            self.assertTupleEqual(d.shape, (1, 100, 101, 107))

            d = output["label_inverted2"]
            # if the interpolation mode is not nearest, accumulated diff should be greater than 10000
            self.assertGreater(torch.sum(d.to(torch.float) - d.to(torch.uint8).to(torch.float)).item(), 10000.0)
            self.assertTupleEqual(d.shape, (1, 100, 101, 107))

        # check labels match
        reverted = engine.state.output[-1]["label_inverted1"].astype(np.int32)
        original = LoadImaged(KEYS)(data[-1])["label"]
        n_good = np.sum(np.isclose(reverted, original, atol=1e-3))
        reverted_name = engine.state.batch[-1]["label_inverted1_meta_dict"]["filename_or_obj"]
        original_name = data[-1]["label"]
        self.assertEqual(reverted_name, original_name)
        print("invert diff", reverted.size - n_good)
        # 25300: 2 workers (cpu, non-macos)
        # 1812: 0 workers (gpu or macos)
        # 1824: torch 1.5.1
        self.assertTrue((reverted.size - n_good) in (25300, 1812, 1824), "diff. in 3 possible values")


if __name__ == "__main__":
    unittest.main()
