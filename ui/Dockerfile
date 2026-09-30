
# Pull base image.
FROM node:20-alpine AS build

# Install packages
RUN apk add --update \
  yarn \
  curl \
  envsubst

# Copy the application code
COPY . /app
WORKDIR /app

RUN yarn install
RUN yarn build
FROM nginx:alpine AS prod
RUN apk add --update \
  envsubst

# COPY --from=build --chown=nginx:nginx /app/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chown=nginx:nginx /app/nginx.conf /app/nginx.conf.template
COPY --from=build --chown=nginx:nginx /app/entrypoint.sh /app/entrypoint.sh
COPY ./cloud9_default_servers.conf /etc/nginx/conf.d/cloud9_default_servers.conf
COPY --from=build --chown=nginx:nginx /app/dist  /usr/share/nginx/html
RUN ls /usr/share/nginx/html/
WORKDIR /app
RUN chown -R nginx:nginx /app && chmod -R 755 /app && \
        chown -R nginx:nginx /var/cache/nginx && \
        chown -R nginx:nginx /var/log/nginx && \
        chown -R nginx:nginx /etc/nginx/conf.d && \
        chown -R nginx:nginx /etc/nginx
RUN cat /etc/nginx/conf.d/cloud9_default_servers.conf
RUN touch /var/run/nginx.pid && \
        chown -R nginx:nginx /var/run/nginx.pid
RUN sed -i 's/<head>/<head>\<script nonce="111dd4a0-4c4e-43a9-8eb4-6446ad2e10c7" language="javascript"\>window.restApiUrl=`\<!--#echo var="restApiUrl"--\>`;window.ffSemanticGroups=`\<!--#echo var="ffSemanticGroups"--\>`;window.ffInsights=`\<!--#echo var="ffInsights"--\>`;window.ffLiveTopology=`\<!--#echo var="ffLiveTopology"--\>`;window.ffStatefulEval=`\<!--#echo var="ffStatefulEval"--\>`;window.ffImpactAssessment=`\<!--#echo var="ffImpactAssessment"--\>`;window.ffWasteEstimation=`\<!--#echo var="ffWasteEstimation"--\>`;window.ffNeurosymbolicEval=`\<!--#echo var="ffNeurosymbolicEval"--\>`;<\/script>/g' /usr/share/nginx/html/index.html

USER nginx
# Add SSI vars
RUN ls /usr/share/nginx/html

ENTRYPOINT ["./entrypoint.sh"]
CMD ["/usr/sbin/nginx", "-g", "daemon off;"]
