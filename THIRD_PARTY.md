# External models and runtime

The optional Step 4 adapter uses Ultralytics and football model weights distributed
through Roboflow's public sports example. Weights and sample footage are downloaded
into ignored `data/` directories and are not redistributed in this Git repository.

- Model download references: https://github.com/roboflow/sports/blob/main/examples/soccer/setup.sh
- Keypoint index semantics: https://github.com/roboflow/sports/blob/main/sports/configs/soccer.py
- Runtime/model licensing: https://www.ultralytics.com/license
- Runtime prediction API: https://docs.ultralytics.com/modes/predict/

Ultralytics publishes AGPL-3.0 and commercial licensing options. This adapter does not
grant permission to deploy these components in a proprietary hosted product. Resolve
the applicable obligations or replace the detector before commercial deployment.
The surrounding project's license is not changed by this document.

The optional foot-review tool additionally uses Ultralytics YOLO11n-pose, with the same
runtime/model licensing considerations. Official model documentation:
https://docs.ultralytics.com/models/yolo11/ and https://docs.ultralytics.com/tasks/pose/.
Pinned download: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt.
The exercised file's SHA-256 is
`869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`.
This hash records the downloaded official asset, not independently signed publisher
authenticity. The adapter checks it before loading. Weights remain in ignored `data/`.
`download-pose-model` is explicit; normal analysis does not download or load this model.

Model SHA-256 hashes are pinned to the files exercised in the Step 4 smoke test, recorded
after downloading, and checked before loading. This detects local/upstream changes, not
independent publisher authenticity. Downloads use the published
provider URLs; filenames/IDs may change upstream. PyTorch checkpoint files are executable
serialization inputs and should only come from trusted publishers. Do not substitute
untrusted checkpoints. `download-models` is an explicit network action; `analyze-video`
does not upload video and expects models already cached.

The keypoint ordering follows Roboflow's documented semantic order. Field dimensions
and marking coordinates are independently specified in meters for a 105×68 m pitch.
Ambiguous penalty-arc intersection indices are omitted rather than inheriting the
example's nonstandard geometric dimensions. Circle cardinal-point predictions are used
as the model's intended semantic landmarks; their perspective accuracy needs evaluation.

Roboflow sports code is MIT licensed. Attribution for the keypoint ordering reference:

Copyright (c) 2024 Roboflow

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
