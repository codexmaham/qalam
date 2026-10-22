# Stroke model

`weights.npz` is a NumPy conversion of the handwriting synthesis network from
Alex Graves, "Generating Sequences With Recurrent Neural Networks". The
conversion and the inference layout follow the public-domain port
[graves-handwriting-mlx](https://github.com/breitburg/graves-handwriting-mlx)
(Unlicense, see `UNLICENSE.txt`). Qalam did not train this model.

Inference is NumPy on one CPU. There is no PyTorch and no MLX dependency, so
the same file runs on Linux and on an Apple Silicon Mac. The network covers a
small Latin alphabet and has no uppercase Q or X. Other scripts stay on the
font renderer.
