# tools

`data/<car>-outline.json` is the traced side profile used by the system map. For the E36 it came from a photogrammetry GLB: project the mesh to the side (Z length, Y up), fit and remove the ground plane, keep faces above the sill plus the outer-skin faces, rasterize, contour with skimage, simplify. Phone scans have nothing usable below the sill, so sill height, wheel positions and wheel size come from factory dimensions (E36 sedan: 4433 mm long, 2700 mm wheelbase, ~630 mm wheel). The GLB itself is not in this repo.
