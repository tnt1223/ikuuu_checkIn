import requests
import json
import re
import os
import time
session = requests.session()

url = os.environ.get('URL')
SMTP= os.environ.get('SMTP')

login_url = '{}/auth/login'.format(url)
check_url = '{}/user/checkin'.format(url)
logout_url = '{}/user/logout'.format(url)

header = {
        'origin': url,
        'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
}
def checkIn(email, passwd, SMTP):
    data = {
            'email': email,
            'passwd': passwd
    }
    try:
        print('账户【'+email+'】进行登录...')
        response = json.loads(session.post(url=login_url,headers=header,data=data).text)
        print(response['msg'])
        # 进行签到
        result = json.loads(session.post(url=check_url,headers=header).text)
        print(result['msg'])
        content = result['msg']
        # 进行推送
        if SMTP != '':
            qqemail('ikuuu签到',content)
            print('推送成功')
        session.get(logout_url)
        content='签到成功'
    except Exception as e:
        print(e)
        content = '签到失败'
        print(content)
        if SMTP != '':
            qqemail('ikuuu签到',content)
        session.get(logout_url)
    return content

def qqemail(subject,text):
    #无需安装第三方库
          #换成你的QQ邮箱SMTP的授权码(QQ邮箱设置里)  设置-> 账户-> SMTP服务
    EMAIL_ADDRESS='821116234@qq.com'      #换成你的邮箱地址
    EMAIL_PASSWORD=SMTP

    import smtplib

    import ssl
    context=ssl.create_default_context()
    sender=EMAIL_ADDRESS               #发件邮箱
    receiver=EMAIL_ADDRESS#"发送到自己邮箱
    from email.message import EmailMessage
    subject=subject
    body=text
    msg=EmailMessage()
    msg['subject']=subject       #邮件主题
    msg['From']=sender
    msg['To']=receiver
    msg.set_content(body)         #邮件内容

    with smtplib.SMTP_SSL("smtp.qq.com",465,context=context) as smtp:
        smtp.login(EMAIL_ADDRESS,EMAIL_PASSWORD)
        smtp.send_message(msg)


if __name__ == '__main__':
    split = os.environ.get('INFO').split(',')
    
    for user in split:
        user_split = user.split('<split>')
        email = user_split[0]
        password = user_split[1]
        #当content为‘签到失败’时，继续尝试登录
        while True:
            content = checkIn(email, password, SMTP)
            if content == '签到成功':
                break
            else:
                print('登录失败，重新登录...')
                
        time.sleep(2)
    
