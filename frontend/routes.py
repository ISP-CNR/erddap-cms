import os, xmltodict, subprocess, json
from flask import render_template, request, url_for, redirect, session, abort, flash, send_from_directory,jsonify
from utils import *
from main import app, SIMPLE_CAPTCHA
import multiauth
#import plotly.graph_objects as go
#from plotly.subplots import make_subplots
import plotly.io 
import numpy as np
import pandas as pd
import xarray as xr

import standardnames

from flask_mail import Mail, Message

mail = Mail(app)

## Site routing
@app.route(f"{URL_PATH}/")
@multiauth.login_required
@multiauth.load_and_authorize_datasets
def index(datasets):
  data = { "datasets" : datasets,
            "url_path" : URL_PATH }

  return render_template('index.html', data=data)

@app.route(f"{URL_PATH}/xml/files")
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def files(dataset):
    back_path = url_for('index')
    file_list = get_dataset_files(dataset)

    data = { "url_path" : URL_PATH, "file_list": file_list, "id": dataset.id }

    return render_template('files.html', data=data, dataset=dataset, back_path=back_path, dashboard_url=DASHBOARD_URL)

@app.route(f"{URL_PATH}/xml/files_show")
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def files_show(dataset):
    back_path = url_for('files')+'?id='+dataset.id
    pd.set_option('colheader_justify', 'center')
    
    filename = os.path.join(dataset.files_dir, clean_user_input(request.args.get('filename')))
    file_stats = os.stat(filename)
  
    split_tup = os.path.splitext(filename)
    if(split_tup[1]==".csv"):
      df = pd.read_csv(filename, sep = find_delimiter(filename))
      for c in [x for x in df.columns if 'time' in x.lower()]:
        
        df[c]=pd.to_datetime(df[c],errors="coerce")
        df=df.dropna()
        df.set_index(c,inplace=True)
        #TO DO units of unixtimestamp
        datecolumn = c
    else:
      #pass
      df = xr.open_dataset(filename).to_dataframe()
  
    # Define a custom formatting function for scientific notation
    large_number_threshold = 1e6
    numeric_columns = df.select_dtypes(include=['number']).columns
    large_number_columns = [col for col in numeric_columns if df[col].max() >= large_number_threshold]


    pd.set_option('display.float_format', lambda x: "{:.2e}".format(x) if x >= large_number_threshold else "{:.4f}".format(x))

    
    
    desc=df.describe()  
    
    desc.loc['count'] = desc.loc['count'].astype(int).astype(str)
    
    #df = df.astype(str)
    #desc.iloc[1:] = desc.iloc[1:].applymap('{:.4f}'.format)
    

    '''
    df_num = df.select_dtypes(include=[float])
    cols=int((len(df_num.columns)+1)/2)
    fig = make_subplots(rows=cols-1, cols=cols)
    
    for i,column in enumerate(df_num):
      fig.add_trace(
          go.Histogram(x=df[column],nbinsx=20,name=column),
          row=i//cols+1, col=i%cols+1
      )
    fig.update_layout(legend=dict(
                              orientation='h',
                              y=1.2,
                              xanchor="center",
                              x=0.5))

    plots=plotly.io.to_html(fig,include_plotlyjs=False, full_html=False)
    
    '''
    data = { "filename": request.args.get('filename'),"filedim":np.round(file_stats.st_size / (1024 * 1024),2), "plots":"Disabled",\
      "describe": desc.to_html(classes='table table-stripped overflow-x-auto text-center')}

    return render_template('files_show.html', data=data, dataset=dataset, back_path=back_path)

@app.route(f"{URL_PATH}/xml/edit")
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def edit(dataset):
    back_path = url_for('index')
    filepath = xmldir+"/"+dataset.filename

    data = { "id": dataset.id, "dataset": dataset, "text": None, "xml": None , "json": None }

    with open(filepath, 'r') as f:
      text = f.read()
      data['text'] = text
      data['xml'] = dataset.mydict
      data['json'] = json.dumps(data['xml'])
      data['current_user'] = multiauth.current_user

    return render_template('edit.html', data=data, standard_names=standardnames.CF_1_6, back_path=back_path, dashboard_url=DASHBOARD_URL)

@app.route(f"{URL_PATH}/users")
@multiauth.login_required
@multiauth.admin_required
@multiauth.active_required
def users():
  back_path = url_for('index')
  users = multiauth.get_users()
  return render_template('users.html', users=users, back_path=back_path)

@app.route(f"{URL_PATH}/users/<id>", methods=['GET', 'POST'])
@multiauth.login_required
@multiauth.admin_required
@multiauth.active_required
def user(id):
  back_path = url_for('users')
  user = multiauth.get_user(id)
  provider=multiauth.get_user_provider(id)
  if request.method == 'POST':
    user.admin = 'admin' in request.form and request.form['admin'] == "on"
    user.active = 'active' in request.form and request.form['active'] == "on"
    permissions = set(request.form.getlist('datasets[]'))
    current_permissions = set([p.dataset_id for p in user.permissions])
    if provider=="local":
      user.name = request.form['name']
      user.affiliation = request.form['affiliation']
              
    elif provider=="orcid":
      user.email = request.form.get('email')
      user.affiliation = request.form['affiliation']
     
    else:
       user.affiliation = request.form['affiliation'] 
      

    for dataset_id in permissions - current_permissions:
      multiauth.add_user_to_dataset(user.id, dataset_id)
    for dataset_id in current_permissions - permissions:
      multiauth.remove_user_from_dataset(user.id, dataset_id)

    new_password = request.form.get('password', None)
    result = multiauth.update_user(user, new_password)

    if result == "ok":
      flash('User successfully updated', 'info')
    else:
      flash(result, 'danger')

  return render_template('user.html', user=user, datasets=get_datasets_list(multiauth.current_user), back_path=back_path)


@app.route(f"{URL_PATH}/profile", methods=['GET', 'POST'])
@multiauth.login_required
@multiauth.active_required
def profile():
  back_path = url_for('index')
  user = multiauth.current_user
  provider=multiauth.get_user_provider(user.id)
  if request.method == 'POST':
    if provider=="local":
      user.name = request.form['name']
      user.affiliation = request.form['affiliation']
      new_password = request.form.get('password')
              
    elif provider=="orcid":
      user.email = request.form.get('email')
      user.affiliation = request.form['affiliation']
     
    else:
       user.affiliation = request.form['affiliation'] 
   
    new_password = request.form.get('password')
    
    result = multiauth.update_user(user, new_password)

    if result == "ok":
      flash('User successfully updated', "info")
    else:
      flash(result, 'danger')

  return render_template('user.html', user=user, datasets=get_datasets_list(multiauth.current_user), back_path=back_path)


@app.route(f"{URL_PATH}/register", methods=['GET', 'POST'])
def register():
    back_path = url_for('index')
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        affiliation = request.form['affiliation'].strip()
                
        c_hash = request.form.get('captcha-hash')
        c_text = request.form.get('captcha-text')
        captcha_result = SIMPLE_CAPTCHA.verify(c_text, c_hash)

        result, user = multiauth.add_user(name, email, password, affiliation, captcha_result)

        if result == "ok":

          flash('Registration successful! You can now log in.', 'success')
          #send email
          subject = 'Hello from ERDDAP CMS!'
          sender = os.environ['ERDDAP_emailSender']
          recipients = [os.environ['ERDDAP_emailEverythingTo']]
          message = f"Hey admin, user id {user.id} ({user.name or 'email not setted'}) just registered!"
          
          try:
            send_mail(app.mailer, subject, message, sender, recipients)
          except Exception as e:
            logger.exception(e)

          return redirect(url_for('login', provider="local"))
        else:
          flash(result, 'danger')
          new_captcha_dict = SIMPLE_CAPTCHA.create()
          return render_template('register.html', captcha = new_captcha_dict, back_path=back_path, name=name,
                                  email=email, password=password, affiliation=affiliation)
    else:
      new_captcha_dict = SIMPLE_CAPTCHA.create()
      return render_template('register.html', captcha = new_captcha_dict, back_path=back_path)

@app.route(f"{URL_PATH}/nc/<path:filename>")
def static_nc(filename):
  print(filename, file=sys.stderr)
  return send_from_directory('static/nc', filename, as_attachment=True)


@app.route("/about")
def about():
    back_path = url_for('index')
    return render_template('about.html', back_path=back_path, dashboard_url=DASHBOARD_URL)
