import os
import sys
import shutil
import argparse
import subprocess
import json
import tempfile
import csv
import io
from access_parser import AccessParser

def parse_table_via_oledb(db_path, table_name):
    # Locate 32-bit PowerShell (required for Jet OLEDB OLE DB Provider)
    sys_root = os.environ.get("SystemRoot", "C:\\Windows")
    powershell_32 = os.path.join(sys_root, "SysWOW64", "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.exists(powershell_32):
        raise FileNotFoundError(f"32-bit PowerShell not found at {powershell_32}")
        
    ps_code = """param (
    [string]$DbPath,
    [string]$Table
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$connStringNoPwd = "Provider=Microsoft.Jet.OLEDB.4.0;Data Source=$DbPath;"
$connStringPwd = "Provider=Microsoft.Jet.OLEDB.4.0;Data Source=$DbPath;Jet OLEDB:Database Password=gamebase;"

$conn = New-Object System.Data.OleDb.OleDbConnection($connStringNoPwd)
try {
    $conn.Open()
} catch {
    # Retry with standard GameBase database password
    $conn = New-Object System.Data.OleDb.OleDbConnection($connStringPwd)
    $conn.Open()
}

try {
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = "SELECT * FROM [$Table]"
    $da = New-Object System.Data.OleDb.OleDbDataAdapter($cmd)
    $dt = New-Object System.Data.DataTable
    $da.Fill($dt) | Out-Null
    
    $columns = $dt.Columns.ColumnName
    $rows = foreach ($row in $dt.Rows) {
        $obj = [ordered]@{}
        foreach ($col in $columns) {
            $obj[$col] = $row.$col
        }
        [PSCustomObject]$obj
    }
    $rows | ConvertTo-Json -Depth 2 -Compress
} catch {
    Write-Error $_.Exception.Message
    exit 1
} finally {
    if ($conn.State -eq "Open") { $conn.Close() }
}
"""
    
    temp_fd, temp_path = tempfile.mkstemp(suffix=".ps1")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(ps_code)
            
        cmd = [
            powershell_32,
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", temp_path,
            "-DbPath", db_path,
            "-Table", table_name
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"PowerShell OLEDB export failed: {result.stderr or result.stdout}")
            
        output = result.stdout.strip()
        if not output:
            return {}
            
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]
            
        if not data:
            return {}
            
        columns = data[0].keys()
        columnar = {col: [] for col in columns}
        for row in data:
            for col in columns:
                columnar[col].append(row.get(col))
        return columnar
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

def parse_table_via_mdbtools(db_path, table_name):
    cmd = ["mdb-export", db_path, table_name]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"mdb-export failed: {result.stderr}")
        
    csv_data = result.stdout.strip()
    if not csv_data:
        return {}
        
    reader = csv.DictReader(io.StringIO(csv_data))
    rows = list(reader)
    if not rows:
        return {}
        
    columns = reader.fieldnames
    columnar = {col: [] for col in columns}
    for row in rows:
        for col in columns:
            columnar[col].append(row.get(col))
    return columnar

def parse_table(db, db_path, table_name):
    try:
        print(f"Parsing '{table_name}' table via access-parser...")
        return db.parse_table(table_name)
    except Exception as e:
        print(f"Warning: access-parser failed to parse '{table_name}': {e}")
        if sys.platform == "win32":
            print(f"Attempting Windows OLEDB fallback for '{table_name}'...")
            try:
                return parse_table_via_oledb(db_path, table_name)
            except Exception as oledb_err:
                print(f"Error: Windows OLEDB fallback failed: {oledb_err}")
                raise e
        else:
            print(f"Attempting macOS/Linux mdbtools fallback for '{table_name}'...")
            try:
                return parse_table_via_mdbtools(db_path, table_name)
            except Exception as mdb_err:
                print(f"Error: mdbtools fallback failed: {mdb_err}")
                raise e

def check_hardlink_support(src_dir, dst_dir):
    # Check if we can create a hardlink between src_dir and dst_dir
    if not os.path.exists(src_dir):
        return False
    os.makedirs(dst_dir, exist_ok=True)
    
    temp_src = os.path.join(src_dir, ".__link_test_src__")
    temp_dst = os.path.join(dst_dir, ".__link_test_dst__")
    
    try:
        with open(temp_src, "w") as f:
            f.write("test")
            
        if os.path.exists(temp_dst):
            os.remove(temp_dst)
            
        os.link(temp_src, temp_dst)
        os.remove(temp_src)
        os.remove(temp_dst)
        return True
    except OSError:
        try:
            os.remove(temp_src)
        except OSError:
            pass
        try:
            os.remove(temp_dst)
        except OSError:
            pass
        return False

def main():
    parser = argparse.ArgumentParser(description="Link GameBase Screenshots and Covers for ES-DE compatibility")
    parser.add_argument("--mdb", required=True, help="Path to GameBase MDB file")
    parser.add_argument("--system-name", required=True, help="ES-DE system folder name (e.g., atari2600)")
    parser.add_argument("--out-dir", default="es_media", help="Output directory for linked media (default: es_media)")
    parser.add_argument("--action", choices=["auto", "link", "copy"], default="auto",
                        help="auto: try hardlink, fallback to copy; link: strictly hardlink; copy: strictly copy")
    parser.add_argument("-y", "--yes", action="store_true", help="Bypass interactive copy confirmation prompts")
    parser.add_argument("--exclude-adult", action="store_true", help="Exclude games flagged as adult content in the database")
    
    args = parser.parse_args()
    
    db_path = os.path.abspath(args.mdb)
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.")
        sys.exit(1)
        
    gb_root = os.path.dirname(db_path)
    screenshots_src_dir = os.path.join(gb_root, "Screenshots")
    extras_src_dir = os.path.join(gb_root, "Extras")
    
    print("==================================================")
    print("      GameBase to ES-DE Media Linking Tool        ")
    print("==================================================")
    print(f"GameBase Root : {gb_root}")
    print(f"ES-DE System  : {args.system_name}")
    print(f"Output Path   : {os.path.abspath(args.out_dir)}")
    print(f"Action Mode   : {args.action.upper()}")
    print("==================================================\n")
    
    if not os.path.exists(screenshots_src_dir) and not os.path.exists(extras_src_dir):
        print(f"Error: Neither Screenshots nor Extras directories were found under GameBase root: {gb_root}")
        sys.exit(1)
        
    # Check link support
    can_link = False
    if os.path.exists(screenshots_src_dir):
        can_link = check_hardlink_support(screenshots_src_dir, args.out_dir)
    elif os.path.exists(extras_src_dir):
        can_link = check_hardlink_support(extras_src_dir, args.out_dir)
        
    print(f"Cross-device / link capability check: Hardlink supported = {can_link}")
    
    # Determine the execution mode based on link support and arguments
    execution_mode = "link"
    if args.action == "copy":
        execution_mode = "copy"
        print("Forced COPY mode enabled.")
    elif args.action == "link":
        execution_mode = "link"
        if not can_link:
            print("\nError: Strictly LINK mode was selected, but hard-linking is not supported (cross-device/different drives).")
            print("Aborting.")
            sys.exit(1)
    else: # auto mode
        if can_link:
            execution_mode = "link"
            print("Hard-linking is supported. Will create zero-space hard links.")
        else:
            execution_mode = "copy"
            print("Hard-linking is NOT supported (directories are on different drives/devices).")
            
            # Interactive prompt before copying files
            if not args.yes and sys.stdin.isatty() and sys.stdout.isatty():
                try:
                    response = input("\nFiles must be COPIED to the target drive (this will consume disk space).\nDo you want to proceed with copying? [y/N]: ").strip().lower()
                    if response not in ["y", "yes"]:
                        print("Operation aborted by user.")
                        sys.exit(0)
                except (KeyboardInterrupt, EOFError):
                    print("\nOperation aborted.")
                    sys.exit(0)
            else:
                print("Proceeding automatically in COPY mode (non-interactive or --yes specified).")
                
    print(f"\nLoading database '{db_path}'...")
    try:
        db = AccessParser(db_path)
    except Exception as e:
        print(f"Error opening database: {e}")
        sys.exit(1)
        
    # 1. Index Extras (Covers)
    covers_lookup = {}
    if "Extras" in db.catalog:
        print("Parsing 'Extras' table...")
        t = parse_table(db, db_path, "Extras")
        if t and "EX_Id" in t:
            for i in range(len(t["EX_Id"])):
                ga_id = t["GA_Id"][i]
                ext_type = t["Type"][i]
                path = t["Path"][i]
                
                # Type 0 is cover art. Index the first valid one per game.
                if ext_type == 0 and ga_id not in covers_lookup:
                    lower_path = path.lower() if path else ""
                    if ("cover\\" in lower_path or "covers\\" in lower_path or "cover/" in lower_path or "covers/" in lower_path) and \
                       (lower_path.endswith(".jpg") or lower_path.endswith(".jpeg") or lower_path.endswith(".png") or lower_path.endswith(".gif")):
                        covers_lookup[ga_id] = path
                        
    # 2. Parse Games
    if "Games" not in db.catalog:
        print("Error: 'Games' table not found in the database. Aborting.")
        sys.exit(1)
        
    print("Reading 'Games' table...")
    g = parse_table(db, db_path, "Games")
    num_rows = len(g["GA_Id"])
    print(f"Total games to process: {num_rows}")
    
    # Setup target directories
    screenshots_dst_dir = os.path.join(args.out_dir, args.system_name, "screenshots")
    covers_dst_dir = os.path.join(args.out_dir, args.system_name, "covers")
    
    os.makedirs(screenshots_dst_dir, exist_ok=True)
    os.makedirs(covers_dst_dir, exist_ok=True)
    
    screenshots_linked = 0
    screenshots_copied = 0
    screenshots_missing = 0
    
    covers_linked = 0
    covers_copied = 0
    covers_missing = 0
    
    print(f"\nProcessing media ({execution_mode.upper()} mode)...")
    
    for i in range(num_rows):
        ga_id = g["GA_Id"][i]
        filename = g["Filename"][i]
        scrnshot = g["ScrnshotFilename"][i]
        cover = covers_lookup.get(ga_id, "")
        
        if not filename:
            continue
            
        # Exclude adult content if flag set
        if args.exclude_adult and "Adult" in g:
            is_adult = g["Adult"][i]
            if is_adult is True or is_adult == 1 or str(is_adult).lower() in ['true', '1']:
                continue
            
        rom_normalized = filename.replace('\\', '/')
        subfolder = os.path.dirname(rom_normalized)
        rom_basename = os.path.splitext(os.path.basename(rom_normalized))[0]
        
        # A. Process Screenshots
        if scrnshot:
            src_scrn_path = os.path.join(screenshots_src_dir, scrnshot)
            if os.path.exists(src_scrn_path):
                ext = os.path.splitext(scrnshot)[1]
                dst_folder = os.path.join(screenshots_dst_dir, subfolder)
                os.makedirs(dst_folder, exist_ok=True)
                dst_scrn_path = os.path.join(dst_folder, rom_basename + ext)
                
                if os.path.exists(dst_scrn_path):
                    os.remove(dst_scrn_path)
                    
                if execution_mode == "link":
                    try:
                        os.link(src_scrn_path, dst_scrn_path)
                        screenshots_linked += 1
                    except OSError as e:
                        print(f"Error linking '{rom_basename}': {e}")
                        screenshots_missing += 1
                else: # copy mode
                    try:
                        shutil.copy2(src_scrn_path, dst_scrn_path)
                        screenshots_copied += 1
                    except Exception as copy_err:
                        print(f"Error copying screenshot for '{rom_basename}': {copy_err}")
                        screenshots_missing += 1
            else:
                screenshots_missing += 1
                
        # B. Process Covers
        if cover:
            src_cover_path = os.path.join(extras_src_dir, cover)
            if os.path.exists(src_cover_path):
                ext = os.path.splitext(cover)[1]
                dst_folder = os.path.join(covers_dst_dir, subfolder)
                os.makedirs(dst_folder, exist_ok=True)
                dst_cover_path = os.path.join(dst_folder, rom_basename + ext)
                
                if os.path.exists(dst_cover_path):
                    os.remove(dst_cover_path)
                    
                if execution_mode == "link":
                    try:
                        os.link(src_cover_path, dst_cover_path)
                        covers_linked += 1
                    except OSError as e:
                        print(f"Error linking cover for '{rom_basename}': {e}")
                        covers_missing += 1
                else: # copy mode
                    try:
                        shutil.copy2(src_cover_path, dst_cover_path)
                        covers_copied += 1
                    except Exception as copy_err:
                        print(f"Error copying cover for '{rom_basename}': {copy_err}")
                        covers_missing += 1
            else:
                covers_missing += 1

    print("\n==================================================")
    print("              Media Linking Summary               ")
    print("==================================================")
    print(f"Screenshots:")
    print(f"  - Hard-linked (0 space) : {screenshots_linked}")
    print(f"  - Copied                : {screenshots_copied}")
    print(f"  - Missing/Not found     : {screenshots_missing}")
    print(f"Covers:")
    print(f"  - Hard-linked (0 space) : {covers_linked}")
    print(f"  - Copied                : {covers_copied}")
    print(f"  - Missing/Not found     : {covers_missing}")
    print("==================================================")
    print("Finished successfully!")

if __name__ == "__main__":
    main()
