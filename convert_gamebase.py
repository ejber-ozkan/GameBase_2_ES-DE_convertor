import os
import sys
import re
import time
import argparse
from access_parser import AccessParser

# Regex to strip XML-incompatible control characters (except tab, newline, carriage return)
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]')

def escape_xml(val):
    if val is None:
        return ""
    val = str(val)
    return (val.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace('"', "&quot;")
               .replace("'", "&apos;"))

def clean_xml_string(val):
    if val is None:
        return ""
    val = str(val)
    val = CONTROL_CHARS.sub('', val)
    return escape_xml(val.strip())

def format_path(path):
    if not path:
        return ""
    # Normalize backslashes to forward slashes for ES-DE cross-platform compatibility
    return path.replace('\\', '/')

def main():
    # Parse Command Line Arguments
    parser = argparse.ArgumentParser(description="Convert GameBase MDB database to ES-DE gamelist.xml")
    parser.add_argument("--mdb", default="GBC_v19.mdb", help="Path to GameBase MDB file (default: GBC_v19.mdb)")
    
    flatten_group = parser.add_mutually_exclusive_group()
    flatten_group.add_argument("--flatten", action="store_true", default=None, help="Force flatten folders in ES-DE (creates flatten.txt)")
    flatten_group.add_argument("--no-flatten", action="store_true", default=None, help="Force disable flattening (deletes flatten.txt)")
    
    args = parser.parse_args()
    
    start_time = time.time()
    
    db_path = args.mdb
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.")
        sys.exit(1)
        
    print(f"Loading GameBase database '{db_path}'...")
    try:
        db = AccessParser(db_path)
    except Exception as e:
        print(f"Error opening database: {e}")
        sys.exit(1)
        
    print("Catalog parsed. Tables found:", list(db.catalog))
    
    # 1. Parse Lookup Tables
    print("Parsing lookup tables...")
    
    # Years
    years_lookup = {}
    if "Years" in db.catalog:
        t = db.parse_table("Years")
        for i in range(len(t["YE_Id"])):
            years_lookup[t["YE_Id"][i]] = t["Year"][i]
            
    # PGenres (Parent Genres)
    pgenres_lookup = {}
    if "PGenres" in db.catalog:
        t = db.parse_table("PGenres")
        for i in range(len(t["PG_Id"])):
            pgenres_lookup[t["PG_Id"][i]] = t["ParentGenre"][i]
            
    # Genres
    genres_lookup = {}
    if "Genres" in db.catalog:
        t = db.parse_table("Genres")
        for i in range(len(t["GE_Id"])):
            ge_id = t["GE_Id"][i]
            genre = t["Genre"][i]
            pg_id = t["PG_Id"][i]
            parent = pgenres_lookup.get(pg_id, "")
            genres_lookup[ge_id] = (parent, genre)
            
    # Developers
    devs_lookup = {}
    if "Developers" in db.catalog:
        t = db.parse_table("Developers")
        for i in range(len(t["DE_Id"])):
            devs_lookup[t["DE_Id"][i]] = t["Developer"][i]
            
    # Publishers
    pubs_lookup = {}
    if "Publishers" in db.catalog:
        t = db.parse_table("Publishers")
        for i in range(len(t["PU_Id"])):
            pubs_lookup[t["PU_Id"][i]] = t["Publisher"][i]
            
    # Extras (Covers/Boxart)
    covers_lookup = {}
    if "Extras" in db.catalog:
        print("Indexing covers from 'Extras' table...")
        t = db.parse_table("Extras")
        for i in range(len(t["EX_Id"])):
            ga_id = t["GA_Id"][i]
            ext_type = t["Type"][i]
            path = t["Path"][i]
            
            # Type 0 is cover art. We only want the first valid cover image per game.
            if ext_type == 0 and ga_id not in covers_lookup:
                lower_path = path.lower() if path else ""
                if ("cover\\" in lower_path or "covers\\" in lower_path or "cover/" in lower_path or "covers/" in lower_path) and \
                   (lower_path.endswith(".jpg") or lower_path.endswith(".jpeg") or lower_path.endswith(".png") or lower_path.endswith(".gif")):
                    covers_lookup[ga_id] = path

    print("Lookup tables indexed successfully.")

    # 2. Process and Write Games
    if "Games" not in db.catalog:
        print("Error: 'Games' table not found in the database. Aborting.")
        sys.exit(1)
        
    print("Reading 'Games' table...")
    g = db.parse_table("Games")
    num_rows = len(g["GA_Id"])
    print(f"Total games to process: {num_rows}")
    
    # Ensure Games folder exists
    games_dir = "Games"
    if not os.path.exists(games_dir):
        os.makedirs(games_dir)
        print(f"Created directory: {games_dir}")
        
    # Handle folder flattening configuration
    flatten_choice = True
    if args.flatten is True:
        flatten_choice = True
    elif args.no_flatten is True:
        flatten_choice = False
    else:
        # Prompt if interactive
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                response = input("\nDo you want to flatten the game list in ES-DE?\n(This hides the subfolders and displays all games in a single flat list) [Y/n]: ").strip().lower()
                if response in ["n", "no"]:
                    flatten_choice = False
            except (KeyboardInterrupt, EOFError):
                print("\nPrompt interrupted, defaulting to Y (flatten).")
        else:
            print("\nNon-interactive environment, defaulting to Y (flatten).")
            
    flatten_file = os.path.join(games_dir, "flatten.txt")
    if flatten_choice:
        with open(flatten_file, "w", encoding="utf-8") as ff:
            ff.write("# Tells ES-DE to display games recursively as a flat list, hiding subfolders.\n")
        print("Folder flattening enabled (created Games/flatten.txt).")
    else:
        if os.path.exists(flatten_file):
            os.remove(flatten_file)
            print("Folder flattening disabled (removed Games/flatten.txt).")
        else:
            print("Folder flattening disabled.")
            
    gamelist_path = os.path.join(games_dir, "gamelist.xml")
    print(f"Writing to {gamelist_path}...")
    
    stats_screenshots = 0
    stats_covers = 0
    stats_ratings = 0
    stats_released = 0
    
    with open(gamelist_path, "w", encoding="utf-8") as f:
        # Write XML Header
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write('<gameList>\n')
        
        for i in range(num_rows):
            ga_id = g["GA_Id"][i]
            name = g["Name"][i]
            filename = g["Filename"][i]
            scrnshot = g["ScrnshotFilename"][i]
            rating = g["Rating"][i]
            comment = g["Comment"][i]
            memo = g["MemoText"][i]
            
            ye_id = g["YE_Id"][i]
            ge_id = g["GE_Id"][i]
            de_id = g["DE_Id"][i]
            pu_id = g["PU_Id"][i]
            
            # Map values from lookups
            year = years_lookup.get(ye_id, "")
            parent_genre, genre = genres_lookup.get(ge_id, ("", ""))
            developer = devs_lookup.get(de_id, "")
            publisher = pubs_lookup.get(pu_id, "")
            cover = covers_lookup.get(ga_id, "")
            
            # Skip records without a filename
            if not filename:
                continue
                
            # ES-DE path for game (parent folder is Games, so relative path is ./...)
            rom_path = "./" + format_path(filename)
            
            f.write('  <game>\n')
            f.write(f'    <path>{clean_xml_string(rom_path)}</path>\n')
            f.write(f'    <name>{clean_xml_string(name)}</name>\n')
            
            # Combine Comment and MemoText into desc
            desc_parts = []
            if comment:
                desc_parts.append(comment)
            if memo:
                desc_parts.append(memo)
            desc = "\n\n".join(desc_parts) if desc_parts else ""
            if desc:
                f.write(f'    <desc>{clean_xml_string(desc)}</desc>\n')
                
            # Screenshot (located in sibling Screenshots folder)
            if scrnshot:
                screenshot_path = "../Screenshots/" + format_path(scrnshot)
                f.write(f'    <image>{clean_xml_string(screenshot_path)}</image>\n')
                stats_screenshots += 1
                
            # Cover Art / Boxart (located in sibling Extras folder)
            if cover:
                cover_path = "../Extras/" + format_path(cover)
                f.write(f'    <thumbnail>{clean_xml_string(cover_path)}</thumbnail>\n')
                stats_covers += 1
                
            # Rating conversion (GameBase 0-5 to ES-DE 0.0-1.0)
            if rating and rating > 0:
                es_rating = min(1.0, max(0.0, float(rating) / 5.0))
                f.write(f'    <rating>{es_rating:.1f}</rating>\n')
                stats_ratings += 1
                
            # Release Date conversion (YYYY0101T000000)
            # Handle special GameBase year mappings
            if year:
                try:
                    year_int = int(year)
                    if 1900 <= year_int <= 2100:
                        release_date = f"{year_int}0101T000000"
                        f.write(f'    <releasedate>{release_date}</releasedate>\n')
                        stats_released += 1
                    elif year_int == 9991: # 198?
                        f.write('    <releasedate>19800101T000000</releasedate>\n')
                        stats_released += 1
                    elif year_int == 9992: # 199?
                        f.write('    <releasedate>19900101T000000</releasedate>\n')
                        stats_released += 1
                    elif year_int == 9993: # 200?
                        f.write('    <releasedate>20000101T000000</releasedate>\n')
                        stats_released += 1
                    elif year_int == 9995: # 197?
                        f.write('    <releasedate>19700101T000000</releasedate>\n')
                        stats_released += 1
                    elif year_int == 9996: # 201?
                        f.write('    <releasedate>20100101T000000</releasedate>\n')
                        stats_released += 1
                    elif year_int == 9997: # 202?
                        f.write('    <releasedate>20200101T000000</releasedate>\n')
                        stats_released += 1
                except ValueError:
                    pass # Ignore unparseable non-integer years
                    
            # Developer mapping
            if developer and developer.lower() not in ["(unknown)", "(none)", "unknown"]:
                f.write(f'    <developer>{clean_xml_string(developer)}</developer>\n')
                
            # Publisher mapping
            if publisher and publisher.lower() not in ["(unknown)", "(none)", "unknown"]:
                f.write(f'    <publisher>{clean_xml_string(publisher)}</publisher>\n')
                
            # Genre mapping (join parent genre and sub genre)
            genre_parts = []
            if parent_genre and parent_genre.lower() not in ["", "[uncategorized]"]:
                genre_parts.append(parent_genre)
            if genre and genre.lower() not in ["", "[uncategorized]"]:
                genre_parts.append(genre)
            full_genre = " - ".join(genre_parts) if genre_parts else ""
            if full_genre:
                f.write(f'    <genre>{clean_xml_string(full_genre)}</genre>\n')
                
            f.write('  </game>\n')
            
        f.write('</gameList>\n')
        
    elapsed = time.time() - start_time
    print(f"\nConversion finished in {elapsed:.2f} seconds!")
    print(f"Output XML written to: {gamelist_path}")
    print(f"Total Games Processed: {num_rows}")
    print(f"Matched Screenshots: {stats_screenshots} ({(stats_screenshots/num_rows)*100:.1f}%)")
    print(f"Matched Cover Arts:  {stats_covers} ({(stats_covers/num_rows)*100:.1f}%)")
    print(f"Games with Ratings:  {stats_ratings} ({(stats_ratings/num_rows)*100:.1f}%)")
    print(f"Games with Release:  {stats_released} ({(stats_released/num_rows)*100:.1f}%)")

if __name__ == "__main__":
    main()
