import logging
import os
import psycopg2
import random

db_name = os.environ["RDS_PODREX_DB"]
user = os.environ["RDS_USER"]
key = os.environ["RDS_SECRET_KEY"]
host = os.environ["RDS_HOST_NAME"]
port = os.environ["RDS_PORT"]

def connect_db():
    """
    Returns connection to AWS RDS set up for this purpose.

    Parameters
    None

    Returns
    conn: psycopg2 connection object
    """
    conn = psycopg2.connect("dbname={} user={} host={} port={} password={}"
                        .format(db_name, user, host, port, key))
    return conn

def update_podcasts(pm, conn):
    """
    Updates podcast metadata table and returns bool of success or failure

    Parameters
    pm: result_dictionary with podcast metadata, from module
    scrape_itunes
    conn: active psycopg2 connection object

    Returns
    True on success, False on failure
    """
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE podcasts "
               "SET podcast_id = (%s), artist_id = (%s), artist_name = (%s), "
               "description = (%s), feed_url = (%s), mean_rating = (%s), "
               "rating_count = (%s), rating_distribution = (%s), "
               "review_count = (%s), genres = (%s), last_update = (%s), "
               "website_url = (%s), artwork = (%s), also_consumed = (%s), "
               "more_by_artist = (%s), top_in_genre = (%s) "
               "WHERE itunes_url = (%s) ",
              (pm["podcast_id"], pm["arist_id"], pm["artist_name"], pm["description"],
               pm["feed_url"], pm["mean_rating"], pm["rating_count"],
               pm["rating_distribution"], pm["review_count"], pm["genres"],
               pm["last_update"], pm["website_url"], pm["artwork"],
               pm["also_consumed"], pm["more_by_artist"], pm["top_in_genre"],
               pm["itunes_url"]))
        conn.commit()
        cursor.close()
        return True
    except:
        logging.exception("failed inside update_podcasts")
        cursor.close()
        conn.rollback() # fix connection
        return False

def update_reviews(review, conn):
    """
    Updates the podcast reviews table and returns bool on success or failure

    Parameters
    review: a single dictionary of review metadata returned from parsing
    function in scrape_itunes module
    conn: active psycopg2 connection

    Returns
    True on success, False on failure
    """
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO reviews "
                       "(podcast_id, username, user_id, review_id, rating, "
                       "title, review_text, vote_count, vote_sum, "
                       "customer_type, date, data_source) "
                       "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                       (review["podcast_id"], review["username"],
                        review["user_id"], review["review_id"],
                        review["rating"], review["title"], review["review_text"],
                        review["vote_count"], review["vote_sum"],
                        review["customer_type"], review["date"],
                        review["data_source"]))
        conn.commit()
        cursor.close()
        return True
    except:
        cursor.close()
        conn.rollback() # fix connection
        logging.exception("failed inside update_reviews")
        return False

def update_episodes(episode, conn):
    """
    Updates the episodes table in the podcast db and returns bool on success

    Parameters
    episode (dict): a dictionary of a single episode metadata
    conn: active psycopg2 connection

    Returns
    True on success, False on failure
    """
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO episodes "
                       "(podcast_id, episode_id, description, name, "
                       "download_url, release_date, popularity) "
                       "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                       (episode["podcast_id"], episode["episode_id"],
                        episode["description"], episode["name"],
                        episode["download_url"], episode["release_date"],
                        episode["popularity"]))
        conn.commit()
        cursor.close()
        return True
    except:
        cursor.close()
        conn.rollback() # fix connection
        logging.exception("failed inside update_episodes")
        return False

def get_unprocessed_podcast(conn, mark_in_progress=False):
    """
    Returns podcast name and url of a single unprocessed podcast
    based on column processed in table podcasts

    Parameters
    conn: active psycopg2 connection object

    Returns
    podcast_name (string) name of returned podcast
    itunes_url (string) url of returned podcast to scrape
    """
    cursor = conn.cursor()
    cursor.execute("SELECT podcast_name, itunes_url "
                   "FROM podcasts WHERE processed = 'false' "
                   "LIMIT 1")
    result = cursor.fetchone()
    podcast_name, itunes_url = result[0], result[1]
    if mark_in_progress:
        cursor.execute("UPDATE podcasts "
                       "SET processed = 'in_progress' "
                       "WHERE itunes_url = %s ", [itunes_url])
    conn.commit()
    cursor.close()
    return podcast_name, itunes_url

def mark_as_itunes(conn, podcast_url):
    """
    Marks a podcast as processed through itunes in the database

    Parameters
    conn: active psycopg2 connection
    podcast_url (str): podcast url to match for updating
    """
    cursor = conn.cursor()
    cursor.execute("UPDATE podcasts "
                   "SET processed = 'itunes' "
                   "WHERE itunes_url = (%s)", [podcast_url])
    conn.commit()
    cursor.close()

def make_unique_id():
    """
    Returns unique alphanumeric id
    """
    unique_id = "".join(random.choice('0123456789abcdefghijklmnopqrstuvwxyz')
                        for i in range(12))

    return unique_id

def set_unique_page(conn, predictions):
    """
    Inserts user prediction data into a database and assigns a unique_id to
    the user. Returns unique_id.

    Parameters
    ----------
    conn: active psycopg2 connection object
    predictions: list user prediction data

    Returns
    -------
    unique_id (str): unique id for user
    """
    cursor = conn.cursor()
    while True:
        unique_id = make_unique_id()
        try:
            cursor.execute("INSERT INTO user_data (user_id, predictions) "
                           "VALUES (%s, %s)",
                           (unique_id, predictions))
            break
        except:
            logging.exception("failed to insert new user")
            conn.rollback()
    conn.commit()
    cursor.close()
    return unique_id

def get_podcast_info(conn, podcast_list):
    """
    Returns list of information about items in spark_pids

    Parameters
    ----------
    conn: active psycopg2 connection object
    podcast_list (list): list of spark_pids for which to retrieve information

    Returns
    -------
    podcast_data (list of lists): list of lists of [podcast_id,
        podcast_name, spark_pid, podcast_description]
    """
    cursor = conn.cursor()
    try:
        cursor.execute("select podcast_id, podcast_name, spark_pid, description, "
                       "itunes_url, stitcher_url, website_url "
                       "from podcasts where spark_pid in %(spark_pids)s",
                       {"spark_pids":tuple(podcast_list)})
        podcasts_raw = cursor.fetchall()
        cursor.close()
        podcasts_data = [list(i) for i in podcasts_raw]
        return podcasts_data
    except:
        logging.exception("failed to get podcast_info")
        conn.rollback()
    finally:
        cursor.close()

def get_prediction_info(conn, unique_id):
    """
    Returns list of information about items in spark_pids

    Parameters
    ----------
    conn: active psycopg2 connection object
    unique_id (str): unique alphanumeric id given to a set of predictions

    Returns
    -------
    recommendation_data (list of lists): list of lists of [podcast_id,
        podcast_name, spark_pid, podcast_description]
    """
    cursor = conn.cursor()
    try:
        cursor.execute("select predictions from user_data where user_id = (%s)",
                       [unique_id])
        results = cursor.fetchone()[0]
        cursor.close()
    except:
        logging.exception("failed to get unique_user_id")
        cursor.close()
        conn.rollback()
        return None
    recommendation_data = get_podcast_info(conn, results)
    return recommendation_data
