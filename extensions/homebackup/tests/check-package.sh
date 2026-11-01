#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
python3 -m py_compile build.py
bash -n backup.sh setup.sh
python3 build.py
pkg=build-mint-homebackup-extension/mint-homebackup-extension_0.1.0_all
for file in "$pkg/usr/bin/homebackup-ext" "$pkg/usr/lib/mint-homebackup-extension/backup.sh" "$pkg/usr/lib/mint-homebackup-extension/run-backup" "$pkg/usr/lib/mint-homebackup-extension/admin" "$pkg/DEBIAN/postinst" "$pkg/DEBIAN/prerm"; do
  bash -n "$file"
done
python3 -m py_compile "$pkg/usr/lib/mint-homebackup-extension/select.py"
python3 - "$pkg/usr/lib/mint-homebackup-extension/select.py" <<'PY'
import importlib.util,sys
spec=importlib.util.spec_from_file_location('retain',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def a(name,date): return {'name':name,'start':date+'T03:00:00'}
data={'archives':[
 a('mint-20261031T010000Z','2026-10-31'),
 a('mint-20261031T020000Z','2026-10-31'),
 a('mint-20261029T010000Z','2026-10-29'),
 a('mint-20261020T010000Z','2026-10-20'),
 a('mint-20260901T010000Z','2026-09-01'),
 a('notes-keep','2026-09-01')
]}
k,d=m.select(data)
assert k==['mint-20261031T020000Z','mint-20261029T010000Z','mint-20261020T010000Z'], (k,d)
assert sorted(d)==['mint-20260901T010000Z','mint-20261031T010000Z'],d
try:m.select({'archives':[a('mint-UNEXPECTED','2026-01-01')]})
except ValueError:pass
else:raise AssertionError('unsafe archive name accepted')
print('retention tests passed')
PY
dpkg-deb --root-owner-group --build "$pkg" ./mint-homebackup-extension_0.1.0_all.deb
name=$(dpkg-deb -f ./mint-homebackup-extension_0.1.0_all.deb Package)
version=$(dpkg-deb -f ./mint-homebackup-extension_0.1.0_all.deb Version)
[[ $name == mint-homebackup-extension && $version == 0.1.0 ]]
echo 'package build and checks passed'