# Factory Productivity

Independent Frappe 16 app for production plans, per-shift reports and line information. Uses the existing `Company`, `Factory`, `Production Line`, `Line Group`, `Product` and `Factory Device` masters from `factory_management`. If `Time Slot` is absent, the pre-model-sync patch creates it. The mobile-first `/productivity` page has Plans, Reports, and Line Information navigation, including report time slots and filtered history. The report form selects the matching plan for the date and line and shows product codes without product names. The former Desk page remains at `/app/productivity-entry`. Both pages use the same offline queue and idempotent sync; the new page uses standard Frappe styling without the .NET theme.

## Install and update

Install `factory_management` first. Add this repository to the bench as app `factory_productivity`, install it on the target site, then run `bench --site <site> migrate`. Pilot should pull the `version-16` branch and run migrate on updates. The app includes patches for `Time Slot` provisioning, role permissions and six default shifts for approved-device companies without configured slots. Existing slot configuration is preserved. No historical records are copied during installation or migration.

## Manual import

Use the separate workbook at `D:\Code\Frappe\migration\outputs\productivity-import-20261116\productivity-data-import.xlsx`. Enter .NET API URL and a temporary JWT in `Thiết lập`, fill `Ánh xạ master` with existing Frappe document names, then choose Data → Refresh All in Excel. Import in this order: `Time Slot`, `Productivity Production Plan`, `Productivity Line Info`, `Productivity Report`. Check empty Link columns and complete `Time Slot` start/end times before import. `Productivity Report` uses child rows `time_slots:time_slot` and `time_slots:finished_quantity`; map these to the Data Import child table columns. Do not use a saved JWT workbook as an archival copy.
