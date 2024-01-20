from flask import Flask, render_template, request, flash, redirect, url_for, session,send_file,make_response,abort,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SubmitField, SelectField,SelectMultipleField
from wtforms.validators import DataRequired
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect
from sqlalchemy.orm import backref,aliased
import io

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///music_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    isadmin = db.Column(db.Integer, default=0, nullable=False)
    iscreate = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    isban = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    playlists = db.relationship('Playlist', backref='creator', lazy=True)

    @property
    def password(self):
        raise AttributeError('Password is not a readable attribute.')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

class JoinAsCreatorForm(FlaskForm):
    submit = SubmitField('Join as Creator')

class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    artist = db.Column(db.String(100), nullable=False)
    lyrics = db.Column(db.Text, nullable=False)
    mp3_binary = db.Column(db.LargeBinary, nullable=True)  # Updated field
    album_id = db.Column(db.Integer, db.ForeignKey('album.id'), nullable=True)

    @property
    def average_rating(self):
        ratings = Rating.query.filter_by(song_id=self.id).all()
        total_ratings = sum(rating.rating for rating in ratings)
        return total_ratings / len(ratings) if len(ratings) > 0 else 0

class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    artist = db.Column(db.String(100), nullable=False,default=lambda: session.get('username'))
    songs = db.relationship('Song', secondary='album_song_association', backref='albums', lazy=True)

album_song_association = db.Table('album_song_association',
    db.Column('album_id', db.Integer, db.ForeignKey('album.id')),
    db.Column('song_id', db.Integer, db.ForeignKey('song.id'))
)

class Rating(db.Model):
    __tablename__ = 'ratings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)

    db.UniqueConstraint('user_id', 'song_id', name='unique_user_song_rating')

    user = db.relationship('User', backref='ratings')
    song = db.relationship('Song', backref='ratings')

class Playlist(db.Model):
    __tablename__ = 'playlist'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    songs = db.relationship('Song', secondary='playlist_song_association', backref='playlists', lazy=True)

playlist_song_association = db.Table('playlist_song_association',
    db.Column('playlist_id', db.Integer, db.ForeignKey('playlist.id')),
    db.Column('song_id', db.Integer, db.ForeignKey('song.id'))
)

class CreateAlbumForm(FlaskForm):
    name = StringField('Album Name', validators=[DataRequired()])
    songs = SelectMultipleField('Select Songs', coerce=int)
    submit = SubmitField('Create Album')

class SearchForm(FlaskForm):
    search_query = StringField('Search', render_kw={"placeholder": "Search"})
    submit = SubmitField('Submit')

class CreatorDashboardForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    artist = StringField('Artist', default=lambda: session.get('username', ''), render_kw={'readonly': True})
    lyrics = TextAreaField('Lyrics', validators=[DataRequired()])
    mp3 = FileField('MP3 File', validators=[FileAllowed(['mp3'], 'Only MP3 files allowed.')])
    submit = SubmitField('Submit')

class CreatePlaylistForm(FlaskForm):
    name = StringField('Playlist Name', validators=[DataRequired()])
    songs = SelectMultipleField('Select Songs', coerce=int)
    submit = SubmitField('Create Playlist')

class AddSongsToPlaylistForm(FlaskForm):
    songs = SelectMultipleField('Select Songs', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Add Songs')

def calculate_average_rating(song_id):
    song = Song.query.get(song_id)
    return song.average_rating

def user_has_rated(song_id):
    user = User.query.filter_by(username=session.get('username')).first()
    if user:
        return Rating.query.filter_by(user_id=user.id, song_id=song_id).first() is not None
    return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()

        if existing_user is None:
            new_user = User(username=username, password=password, isadmin=0)
            db.session.add(new_user)

            try:
                db.session.commit()
                flash(f"Registration successful! Welcome, {username}!")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")
        else:
            error = "Username already exists. Please choose a different one."

    return render_template('register.html', error=error)

@app.route('/login/user', methods=['GET', 'POST'])
def login_user():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username, isadmin=0).first()

        if user:
            if user.isban == 1:
                error = "Account has been banned. Please contact support for further assistance."
            elif user.verify_password(password):
                session['username'] = username
                return redirect(url_for('user_dashboard'))
            else:
                error = "Invalid username or password. Please try again."
        else:
            error = "Invalid username or password. Please try again."

    return render_template('login.html', error=error, is_user_login=True)

@app.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        admin = User.query.filter_by(username=username, isadmin=1).first()

        if admin and admin.verify_password(password):
            return redirect(url_for('admin_dashboard'))
        else:
            error = "Invalid username or password. Please try again."

    return render_template('login.html', error=error, is_admin_login=True)

@app.route('/dashboard/user', methods=['GET', 'POST'])
def user_dashboard():
    username = session.get('username')

    if username:
        user = User.query.filter_by(username=username).first()

        form = JoinAsCreatorForm()

        if request.method == 'POST' and user and user.iscreate == 0 and form.validate_on_submit():
            user.iscreate = 1

            try:
                db.session.commit()
                flash("Congratulations! You've joined the platform as a creator.")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")

            return redirect(url_for('user_dashboard'))

        songs = Song.query.all()
        albums = Album.query.all()

        return render_template('user_dashboard.html', username=username, is_creator=user.iscreate, form=form, songs=songs, albums=albums)
    else:
        return redirect(url_for('login_user'))

@app.route('/dashboard/creator', methods=['GET', 'POST'])
def creator_dashboard():
    creator = User.query.filter_by(username=session.get('username')).first()

    if creator and creator.iscreate == 1:
        songs = Song.query.filter_by(artist=creator.username).all()
        form = CreatorDashboardForm()
        albums = Album.query.filter_by(artist=creator.username).all()
          
        if form.validate_on_submit():
            print("Form submitted successfully!")
            print(f"Title: {form.title.data}")
            print(f"Artist: {form.artist.data}")
            print(f"Lyrics: {form.lyrics.data}")
            print(f"MP3 File: {form.mp3.data.filename}")

            max_song_id = db.session.query(db.func.max(Song.id)).scalar()
            new_song_id = 1 if max_song_id is None else max_song_id + 1

            mp3_file = form.mp3.data.read()

            new_song = Song(
                id=new_song_id,
                title=form.title.data,
                artist=creator.username,
                lyrics=form.lyrics.data,
                mp3_binary=mp3_file
            )

            db.session.add(new_song)

            try:
                db.session.commit()
                flash("Song uploaded successfully!")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")

            return redirect(url_for('creator_dashboard'))

        else:
            print("Form validation errors:")
            print(form.errors)

        return render_template('creator_dashboard.html', form=form, songs=songs, albums=albums)

    else:
        return redirect(url_for('login_user'))

@app.route('/dashboard/creator/modify/<int:song_id>', methods=['GET', 'POST'])
def modify_song(song_id):
    creator = User.query.filter_by(username=session.get('username')).first()

    if creator and creator.iscreate == 1:
        song_to_modify = Song.query.get(song_id)

        if song_to_modify and song_to_modify.artist == creator.username:
            form = CreatorDashboardForm(obj=song_to_modify)

            if form.validate_on_submit():
                print("Form submitted successfully!")
                print(f"Title: {form.title.data}")
                print(f"Artist: {form.artist.data}")
                print(f"Lyrics: {form.lyrics.data}")
                
                song_to_modify.title = form.title.data
                song_to_modify.lyrics = form.lyrics.data

                
                db.session.commit()
                flash("Song updated successfully!")

                return redirect(url_for('creator_dashboard'))

            else:
                print("Form validation errors:")
                print(form.errors)

            return render_template('modify_song.html', form=form, song_id=song_id)

        else:
            flash("Song not found or you don't have permission to modify it.")
            return redirect(url_for('creator_dashboard'))

    else:
        return redirect(url_for('login_user'))
    
@app.route('/dashboard/creator/delete/<int:song_id>', methods=['GET'])
def delete_song(song_id):
    creator = User.query.filter_by(username=session.get('username')).first()

    if creator and creator.iscreate == 1:
        song_to_delete = Song.query.get(song_id)

        if song_to_delete and song_to_delete.artist == creator.username:
            try:
                db.session.delete(song_to_delete)
                db.session.commit()
                flash("Song deleted successfully!")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")

            return redirect(url_for('creator_dashboard'))

@app.route('/dashboard/creator/create_album', methods=['GET', 'POST'])
def create_album():
    creator = User.query.filter_by(username=session.get('username')).first()

    if creator and creator.iscreate == 1:
        user_songs = Song.query.filter_by(artist=creator.username).all()

        form = CreateAlbumForm()
        form.songs.choices = [(song.id, song.title) for song in user_songs]

        if form.validate_on_submit():
            new_album = Album(name=form.name.data, artist=creator.username)  

            db.session.add(new_album)
            db.session.commit()

            selected_song_ids = form.songs.data
            selected_songs = Song.query.filter(Song.id.in_(selected_song_ids)).all()

            new_album.songs.extend(selected_songs)

            try:
                db.session.commit()
                flash("Album created successfully!")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")

            return redirect(url_for('creator_dashboard'))

        return render_template('create_album.html', form=form)

    else:
        return redirect(url_for('login_user'))

@app.route('/dashboard/creator/modify_album/<int:album_id>', methods=['GET', 'POST'])
def modify_album(album_id):
    creator = User.query.filter_by(username=session.get('username')).first()

    if creator and creator.iscreate == 1:
        album_to_modify = Album.query.get(album_id)

        if album_to_modify and album_to_modify.artist == creator.username:
            form = CreateAlbumForm()
            user_songs = Song.query.filter_by(artist=creator.username).all()
            form.songs.choices = [(song.id, song.title) for song in user_songs]

            if request.method == 'POST' and form.validate_on_submit():
                album_to_modify.name = form.name.data
                album_to_modify.songs.clear()
                selected_song_ids = form.songs.data
                selected_songs = Song.query.filter(Song.id.in_(selected_song_ids)).all()
                album_to_modify.songs.extend(selected_songs)

                try:
                    db.session.commit()
                    flash("Album updated successfully!")
                except Exception as e:
                    db.session.rollback()
                    flash("An error occurred. Please try again.")
                    print(f"Error: {e}")

                return redirect(url_for('creator_dashboard'))

            form.name.data = album_to_modify.name
            form.songs.data = [song.id for song in album_to_modify.songs]

            return render_template('modify_album.html', form=form, album_id=album_id)

    return redirect(url_for('login_user'))

@app.route('/dashboard/creator/delete_album/<int:album_id>', methods=['GET'])
def delete_album(album_id):
    creator = User.query.filter_by(username=session.get('username')).first()

    if creator and creator.iscreate == 1:
        album_to_delete = Album.query.get(album_id)

        if album_to_delete and album_to_delete.artist == creator.username:
            try:
                db.session.delete(album_to_delete)
                db.session.commit()
                flash("Album deleted successfully!")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")

            return redirect(url_for('creator_dashboard'))

    return redirect(url_for('login_user'))

@app.route('/dashboard/admin', methods=['GET', 'POST'])
def admin_dashboard():
    total_users = User.query.filter_by(isadmin=0 ,isban =0).count()
    total_creators = User.query.filter_by(iscreate=1 ,isban =0).count()
    total_songs = Song.query.count()
    total_albums = Album.query.count()

    return render_template('admin_dashboard.html', total_users=total_users, total_creators=total_creators, total_songs=total_songs, total_albums=total_albums)

@app.route('/user_list', methods=['GET', 'POST'])
def user_list():
    users = User.query.all()
    return render_template('user_list.html', users=users)

@app.route('/song_list', methods=['GET', 'POST'])
def song_list():
    songs = Song.query.all()
    return render_template('song_list.html', songs=songs)

@app.route('/album_list', methods=['GET', 'POST'])
def album_list():
    albums = Album.query.all()
    return render_template('album_list.html', albums=albums)

@app.route('/ban_user/<int:user_id>', methods=['POST'])
def ban_user(user_id):
    user_to_ban = User.query.get(user_id)

    if user_to_ban:
        user_to_ban.isban = 1

        if user_to_ban.iscreate == 1:
            Song.query.filter_by(artist=user_to_ban.username).delete()
            Album.query.filter_by(artist=user_to_ban.username).delete()

    try:
        db.session.commit()
        flash("User banned successfully!")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred. Please try again.")
        print(f"Error: {e}")

    return redirect(url_for('user_list'))

@app.route('/dashboard/admin/delete/<int:song_id>', methods=['GET'])
def delete_song2(song_id):
    song_to_delete = Song.query.get(song_id)
    try:
        db.session.delete(song_to_delete)
        db.session.commit()
        flash("Song deleted successfully!")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred. Please try again.")
        print(f"Error: {e}")

    return redirect(url_for('song_list'))

@app.route('/dashboard/admin/delete_album/<int:album_id>', methods=['GET'])
def delete_album2(album_id):
    album_to_delete = Album.query.get(album_id)

    try:
        db.session.delete(album_to_delete)
        db.session.commit()
        flash("Album deleted successfully!")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred. Please try again.")
        print(f"Error: {e}")
        return redirect(url_for('admin_dashboard'))

    return redirect(url_for('album_list'))

@app.route('/song/<int:song_id>', methods=['GET'])
def song_details(song_id):
    song = Song.query.get(song_id)
    average_rating = calculate_average_rating(song_id) 
    has_rated = user_has_rated(song_id) 

    is_admin = False
    username = session.get('username')
    if username:
        user = User.query.filter_by(username=username).first()
        if user and user.isadmin == 1:
            is_admin = True

    return render_template('song_details.html', song=song, average_rating=average_rating, has_rated=has_rated,is_admin=is_admin)

@app.route('/get_mp3/<int:song_id>', methods=['GET'])
def get_mp3(song_id):
    song = Song.query.get(song_id)

    if song and song.mp3_binary:
        response = make_response(song.mp3_binary)
        response.headers['Content-Type'] = 'audio/mp3'
        response.headers['Content-Disposition'] = f'inline; filename={song.title}.mp3'
        return response
    else:
        abort(404) 

@app.route('/rate_song/<int:song_id>', methods=['POST'])
def rate_song(song_id):
    user = User.query.filter_by(username=session.get('username')).first()
    if user:
        existing_rating = Rating.query.filter_by(user_id=user.id, song_id=song_id).first()

        if existing_rating:
            existing_rating.rating = int(request.form['rating'])
        else:
            new_rating = Rating(user_id=user.id, song_id=song_id, rating=int(request.form['rating']))
            db.session.add(new_rating)

        try:
            db.session.commit()
            flash("Rating submitted successfully!")
        except Exception as e:
            db.session.rollback()
            flash("An error occurred. Please try again.")
            print(f"Error: {e}")
    else:
        flash("User not found. Please log in.")

    return redirect(url_for('song_details', song_id=song_id))

@app.route('/dashboard/user/create_playlist', methods=['GET', 'POST'])
def create_playlist():
    db.create_all()
    username = session.get('username')
    user = User.query.filter_by(username=username).first()

    if user:
        user_songs = Song.query.all()
        form = CreatePlaylistForm()
        form.songs.choices = [(song.id, song.title) for song in user_songs]

        if form.validate_on_submit():
            new_playlist = Playlist(name=form.name.data, creator=user)
            db.session.add(new_playlist)
            db.session.commit()

            selected_song_ids = form.songs.data
            selected_songs = Song.query.filter(Song.id.in_(selected_song_ids)).all()

            new_playlist.songs.extend(selected_songs)

            try:
                db.session.commit()
                flash("Playlist created successfully!")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")

            return redirect(url_for('playlist_list'))

        return render_template('create_playlist.html', form=form)

    else:
        return redirect(url_for('login_user'))

    
@app.route('/playlist_list', methods=['GET', 'POST'])
def playlist_list():
    username = session.get('username')
    if username:
        user = User.query.filter_by(username=username).first()
        if user:
            playlists = Playlist.query.filter_by(creator=user).all()
            return render_template('playlist_list.html', playlists=playlists)
    flash("User not found. Please log in.")
    return redirect(url_for('login_user'))

@app.route('/delete_playlist/<int:playlist_id>', methods=['GET'])
def delete_playlist(playlist_id):
    username = session.get('username')
    if not username:
        flash("User not found. Please log in.")
        return redirect(url_for('login_user'))

    user = User.query.filter_by(username=username).first()
    playlist = Playlist.query.get(playlist_id)

    if not playlist or not user:
        flash("Playlist or user not found.")
        return redirect(url_for('playlist_list'))

    if playlist.creator != user:
        flash("You don't have permission to delete this playlist.")
        return redirect(url_for('playlist_list'))

    try:
        db.session.delete(playlist)
        db.session.commit()
        flash("Playlist deleted successfully!")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred. Please try again.")
        print(f"Error: {e}")

    return redirect(url_for('playlist_list'))

@app.route('/playlist/<int:playlist_id>/songs', methods=['GET'])
def playlist_songs(playlist_id):
    username = session.get('username')
    if not username:
        flash("User not found. Please log in.")
        return redirect(url_for('login_user'))

    user = User.query.filter_by(username=username).first()
    playlist = Playlist.query.get(playlist_id)

    if not playlist or not user:
        flash("Playlist or user not found.")
        return redirect(url_for('playlist_list'))

    if playlist.creator != user:
        flash("You don't have permission to view songs in this playlist.")
        return redirect(url_for('playlist_list'))

    songs = playlist.songs
    return render_template('playlist_songs.html', playlist=playlist, songs=songs)

@app.route('/album/<int:album_id>/songs', methods=['GET'])
def album_songs(album_id):
    album = Album.query.get(album_id)

    if album:
        songs = album.songs
        return render_template('album_songs.html', album=album, songs=songs)
    else:
        flash("Album not found.")
        return redirect(url_for('user_dashboard'))
    
@app.route('/playlist/<int:playlist_id>/add_songs', methods=['GET', 'POST'])
def add_songs_to_playlist(playlist_id):
    playlist = Playlist.query.get(playlist_id)

    if playlist:
        all_songs = Song.query.all()
        songs_not_in_playlist = [song for song in all_songs if song not in playlist.songs]

        form = AddSongsToPlaylistForm()
        form.songs.choices = [(song.id, song.title) for song in songs_not_in_playlist]

        if form.validate_on_submit():
            selected_song_ids = form.songs.data
            selected_songs = Song.query.filter(Song.id.in_(selected_song_ids)).all()

            playlist.songs.extend(selected_songs)

            try:
                db.session.commit()
                flash("Songs added to the playlist successfully!")
            except Exception as e:
                db.session.rollback()
                flash("An error occurred. Please try again.")
                print(f"Error: {e}")

            return redirect(url_for('playlist_songs', playlist_id=playlist_id))

        return render_template('add_songs_to_playlist.html', form=form, playlist_id=playlist_id)

    flash("Playlist not found.")
    return redirect(url_for('user_dashboard'))


@app.route('/search', methods=['POST'])
def search():
    search_form = SearchForm()
    search_query = search_form.search_query.data

    songs = Song.query.filter(
        (Song.title.ilike(f"%{search_query}%")) |
        (Song.artist.ilike(f"%{search_query}%")) |
        (Song.lyrics.ilike(f"%{search_query}%"))
    ).all()

    albums = Album.query.filter(
        (Album.name.ilike(f"%{search_query}%")) |
        (Album.artist.ilike(f"%{search_query}%")) |
        Album.songs.any(Song.title.ilike(f"%{search_query}%"))
    ).all()

    return render_template('search_results.html', songs=songs, albums=albums, form=search_form)


if __name__ == '__main__':
    app.run(debug=True)


with app.app_context():
    db.create_all()
    inspector = inspect(db.engine)
    existing_database = inspector.has_table("playlist")

    if existing_database:
        print("Connected to an existing database: music_app.db")

    else:
        print("Created a new database: music_app.db")
        db.create_all(bind='album_song_association')
if __name__ == '__main__':
    app.run(debug=True)