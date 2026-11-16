# Current finite-radius grid capture

`radius-grid-current.png` is the root-reviewed 1280 × 1000 local browser capture from the 2026-11-16 portfolio task. It was copied unchanged from `captures/camwright-radius-grid-current-1280.png`, captured on the installed 0.2.2.dev0 preview at port 50128.

The bundled synthetic motion uses base radii 20/25/30 mm and roller radii 4/5/6 mm, with budget 64. All nine pairs were checked: three Fail and six Pass, with no unresolved pairs. The 25/4 mm pair has the minimum zero-lift pitch radius of 29 mm within that declared grid. This is the actual application result, not a mockup or a physical cam measurement.

The root inspected the capture. Source-bound identities at capture:

- PNG SHA-256: `c5fb1655f9bd201b296ef192de8f244e2ad6e1dd91d84b89de2f7cf20204ba29`
- Packaged app.js SHA-256: `8ee3a6bba39bd9bfd4daff7530f3c70469580d6ab87f3d55e7edf8bed77d8d58`
- Packaged styles.css SHA-256: `799c63b7f647602af29392647e7508039102137260964a0debe8d6df09c6f7fa`
- Packaged index.html SHA-256: `304ae168bf35164b89a8fc944011f026fde4afebe8968db4b0138cfa2f1e36e9`
- Captured installed wheel SHA-256: `26ec83fd4520d3319cf9cc5b8c6b0c552ee5dcee18dd596f13fbd9764e15ebef`

The documentation-only successor retains these UI assets byte for byte. The existing failed-check hero and original captures remain separate evidence; they were not replaced or relabeled as this run.
